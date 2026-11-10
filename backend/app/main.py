from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine
from .models import Movie, Review
from .schemas import MovieCreate, MovieRead, RatingRead, ReviewCreate, ReviewRead
from .sentiment import analyze_sentiment


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="영화 리뷰 감성 분석 API",
    summary="영화 정보와 리뷰를 관리하고 한국어 감성을 분석하는 API",
    description=(
        "## 서비스 개요\n"
        "영화와 사용자 리뷰를 관리합니다. 리뷰 등록 요청은 한국어 감성 분류 모델을 실행한 뒤 "
        "긍정/부정 라벨과 점수, 신뢰도를 리뷰 데이터와 함께 저장합니다.\n\n"
        "## 점수 해석\n"
        "`sentiment_score`는 긍정 확률에서 부정 확률을 뺀 값으로 -1.0~1.0 범위입니다. "
        "`average_rating`은 이 값을 5점 척도로 환산한 요약값이며 사용자가 직접 매긴 별점이 아닙니다.\n\n"
        "## 데이터 정책\n"
        "영화 삭제 시 해당 영화에 속한 리뷰도 함께 삭제됩니다. 리뷰 내용은 최대 5,000자입니다. "
        "리뷰 생성 시 모델을 사용할 수 없으면 리뷰를 저장하지 않고 503을 반환합니다."
    ),
    version="1.0.0",
    openapi_tags=[
        {"name": "영화", "description": "영화 등록, 조회 및 삭제"},
        {"name": "리뷰", "description": "리뷰 등록, 조회 및 삭제. 등록 시 감성 분석이 실행됩니다."},
        {"name": "평점", "description": "리뷰 감성 점수의 영화별 평균과 환산 평점"},
        {"name": "시스템", "description": "API 상태 확인"},
    ],
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _movie_read(db: Session, movie: Movie) -> MovieRead:
    result = db.execute(
        select(func.avg(Review.sentiment_score), func.count(Review.id)).where(Review.movie_id == movie.id)
    ).one()
    avg_score, count = result
    score = round(float(avg_score), 4) if avg_score is not None else None
    rating = round((score + 1) * 2.5, 2) if score is not None else None
    return MovieRead.model_validate(movie).model_copy(
        update={"average_sentiment_score": score, "average_rating": rating, "review_count": count}
    )


@app.get("/health", summary="API 상태 확인", description="백엔드 서버의 실행 상태를 확인합니다.", tags=["시스템"])
def health():
    return {"status": "ok"}


@app.post("/movies", response_model=MovieRead, status_code=status.HTTP_201_CREATED,
          summary="영화 등록", description="제목과 선택 영화 정보를 등록합니다. 생성된 영화 ID와 현재 평균 감성 평점을 반환합니다.", tags=["영화"])
def create_movie(payload: MovieCreate, db: Session = Depends(get_db)):
    movie = Movie(**payload.model_dump(mode="python"))
    db.add(movie)
    db.commit()
    db.refresh(movie)
    return _movie_read(db, movie)


@app.get("/movies", response_model=list[MovieRead],
         summary="영화 전체 조회", description="등록된 영화를 최신 등록 순으로 반환합니다. 각 항목에 리뷰 수와 감성 평균을 포함합니다.", tags=["영화"])
def list_movies(db: Session = Depends(get_db)):
    movies = db.scalars(select(Movie).order_by(Movie.created_at.desc())).all()
    return [_movie_read(db, movie) for movie in movies]


@app.get("/movies/{movie_id}", response_model=MovieRead,
         summary="영화 상세 조회", description="영화 ID로 상세 정보와 평균 감성 평점을 조회합니다.",
         responses={404: {"description": "해당 ID의 영화가 없습니다."}}, tags=["영화"])
def get_movie(movie_id: int, db: Session = Depends(get_db)):
    movie = db.get(Movie, movie_id)
    if movie is None:
        raise HTTPException(status_code=404, detail="영화를 찾을 수 없습니다.")
    return _movie_read(db, movie)


@app.delete("/movies/{movie_id}", status_code=status.HTTP_204_NO_CONTENT,
            summary="영화 삭제", description="영화와 그 영화에 연결된 리뷰를 함께 삭제합니다. 성공 시 본문 없는 204를 반환합니다.",
            responses={404: {"description": "해당 ID의 영화가 없습니다."}}, tags=["영화"])
def delete_movie(movie_id: int, db: Session = Depends(get_db)):
    movie = db.get(Movie, movie_id)
    if movie is None:
        raise HTTPException(status_code=404, detail="영화를 찾을 수 없습니다.")
    db.delete(movie)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/reviews", response_model=ReviewRead, status_code=status.HTTP_201_CREATED,
          summary="리뷰 등록 및 감성 분석", description="영화 ID, 작성자, 리뷰 본문을 받아 감성을 분석하고 결과와 함께 저장합니다.",
          responses={404: {"description": "리뷰가 연결될 영화가 없습니다."},
                     503: {"description": "감성 분석 모델을 사용할 수 없습니다. 리뷰는 저장되지 않습니다."}}, tags=["리뷰"])
def create_review(payload: ReviewCreate, db: Session = Depends(get_db)):
    if db.get(Movie, payload.movie_id) is None:
        raise HTTPException(status_code=404, detail="영화를 찾을 수 없습니다.")
    try:
        sentiment = analyze_sentiment(payload.content)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="감성 분석 모델을 준비하지 못했습니다. 백엔드 로그를 확인해 주세요.",
        ) from exc
    review = Review(
        **payload.model_dump(),
        sentiment_label=sentiment["label"],
        sentiment_score=sentiment["score"],
        sentiment_confidence=sentiment["confidence"],
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


@app.get("/reviews", response_model=list[ReviewRead],
         summary="리뷰 조회", description="기본은 전체 리뷰를 최신순으로 반환합니다. `movie_id`로 영화 필터를 지정하고 `limit`으로 건수를 제한할 수 있습니다.", tags=["리뷰"])
def list_reviews(
    movie_id: int | None = None,
    limit: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
):
    query = select(Review).order_by(Review.created_at.desc(), Review.id.desc())
    if movie_id is not None:
        query = query.where(Review.movie_id == movie_id)
    if limit is not None:
        query = query.limit(limit)
    return db.scalars(query).all()


@app.get("/movies/{movie_id}/reviews", response_model=list[ReviewRead],
         summary="영화별 리뷰 조회", description="특정 영화의 리뷰를 최신순으로 반환합니다. `limit`은 선택 입력입니다.",
         responses={404: {"description": "해당 ID의 영화가 없습니다."}}, tags=["리뷰"])
def list_movie_reviews(
    movie_id: int,
    limit: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
):
    if db.get(Movie, movie_id) is None:
        raise HTTPException(status_code=404, detail="영화를 찾을 수 없습니다.")
    query = select(Review).where(Review.movie_id == movie_id).order_by(
        Review.created_at.desc(), Review.id.desc()
    )
    if limit is not None:
        query = query.limit(limit)
    return db.scalars(query).all()


@app.delete("/reviews/{review_id}", status_code=status.HTTP_204_NO_CONTENT,
            summary="리뷰 삭제", description="리뷰 ID에 해당하는 리뷰를 삭제합니다. 성공 시 본문 없는 204를 반환합니다.",
            responses={404: {"description": "해당 ID의 리뷰가 없습니다."}}, tags=["리뷰"])
def delete_review(review_id: int, db: Session = Depends(get_db)):
    review = db.get(Review, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="리뷰를 찾을 수 없습니다.")
    db.delete(review)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/movies/{movie_id}/rating", response_model=RatingRead,
         summary="영화 평균 평점 조회", description="리뷰 감성 점수의 평균과 이를 5점 척도로 환산한 값, 리뷰 수를 반환합니다.",
         responses={404: {"description": "해당 ID의 영화가 없습니다."}}, tags=["평점"])
def get_movie_rating(movie_id: int, db: Session = Depends(get_db)):
    if db.get(Movie, movie_id) is None:
        raise HTTPException(status_code=404, detail="영화를 찾을 수 없습니다.")
    avg_score, count = db.execute(
        select(func.avg(Review.sentiment_score), func.count(Review.id)).where(Review.movie_id == movie_id)
    ).one()
    score = round(float(avg_score), 4) if avg_score is not None else None
    return RatingRead(
        movie_id=movie_id,
        average_sentiment_score=score,
        average_rating=round((score + 1) * 2.5, 2) if score is not None else None,
        review_count=count,
    )
