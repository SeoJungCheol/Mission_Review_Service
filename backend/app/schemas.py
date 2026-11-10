from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class MovieCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200, description="영화 제목", examples=["기생충"])
    release_date: date | None = Field(default=None, description="개봉일", examples=["2019-05-30"])
    director: str | None = Field(default=None, max_length=120, description="감독 이름")
    genre: str | None = Field(default=None, max_length=120, description="장르")
    poster_url: str | None = Field(default=None, description="포스터 이미지의 공개 HTTP(S) URL")

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("영화 제목을 입력해 주세요.")
        return value

    @field_validator("poster_url")
    @classmethod
    def validate_poster_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return str(HttpUrl(value.strip()))


class MovieRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="영화 고유 ID")
    title: str = Field(description="영화 제목")
    release_date: date | None = Field(description="개봉일")
    director: str | None = Field(description="감독")
    genre: str | None = Field(description="장르")
    poster_url: str | None = Field(description="포스터 URL")
    created_at: datetime = Field(description="등록 시각")
    average_sentiment_score: float | None = Field(default=None, description="리뷰 감성 점수 평균(-1~1)")
    average_rating: float | None = Field(default=None, description="감성 점수의 5점 환산값")
    review_count: int = Field(default=0, description="연결된 리뷰 수")


class ReviewCreate(BaseModel):
    movie_id: int = Field(description="리뷰를 연결할 영화 ID", examples=[1])
    author: str = Field(min_length=1, max_length=80, description="작성자 표시 이름", examples=["필름팬"])
    content: str = Field(min_length=2, max_length=5000, description="감성 분석을 수행할 한국어 리뷰 본문", examples=["배우들의 연기와 연출이 정말 인상적이었어요."])

    @field_validator("author", "content")
    @classmethod
    def trim_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("빈 값은 등록할 수 없습니다.")
        return value


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="리뷰 고유 ID")
    movie_id: int = Field(description="연결된 영화 ID")
    author: str = Field(description="작성자 이름")
    content: str = Field(description="리뷰 본문")
    sentiment_label: str = Field(description="감성 분류 결과(긍정/부정)")
    sentiment_score: float = Field(description="긍정 확률 - 부정 확률(-1~1)")
    sentiment_confidence: float = Field(description="분류 결과의 신뢰도(0~1)")
    created_at: datetime = Field(description="리뷰 등록 시각")


class RatingRead(BaseModel):
    movie_id: int = Field(description="영화 고유 ID")
    average_sentiment_score: float | None = Field(description="리뷰 감성 점수의 산술 평균")
    average_rating: float | None = Field(description="감성 평균의 5점 환산값")
    review_count: int = Field(description="평균 계산에 사용한 리뷰 수")


class SentimentResult(BaseModel):
    label: str
    score: float
    confidence: float
    model: str
