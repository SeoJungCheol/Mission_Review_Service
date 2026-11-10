from __future__ import annotations

import os
from datetime import datetime

import requests
import streamlit as st


st.set_page_config(page_title="필름로그 | 영화 리뷰", page_icon="🎬", layout="wide")


def api_url() -> str:
    try:
        return st.secrets.get("API_BASE_URL", os.getenv("API_BASE_URL", "http://localhost:8000")).rstrip("/")
    except (FileNotFoundError, KeyError):
        return os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")


API = api_url()


class ApiError(Exception):
    pass


def api(method: str, path: str, **kwargs):
    try:
        response = requests.request(method, f"{API}{path}", timeout=60, **kwargs)
        if not response.ok:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise ApiError(f"API 오류 ({response.status_code}): {detail}")
        return response.json() if response.content else None
    except requests.RequestException as exc:
        raise ApiError(f"백엔드에 연결할 수 없습니다: {exc}") from exc


def show_error(error: Exception):
    st.error(str(error))


st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Noto+Sans+KR:wght@400;500;600;700;800&display=swap');
.stApp { background: #101114; color: #f4f1eb; font-family: 'DM Sans','Noto Sans KR',sans-serif; }
.block-container { max-width: 1200px; padding-top: 2.1rem; }
[data-testid="stHeader"] { background: transparent; }
.hero { padding: 2rem 0 1.4rem; border-bottom: 1px solid #34353a; margin-bottom: 1.7rem; }
.eyebrow { color: #e4b76a; letter-spacing: .19em; font-size: .72rem; font-weight: 700; }
.hero h1 { font-size: clamp(2.7rem,6vw,5rem); letter-spacing: -.065em; margin: .3rem 0; color: #fffaf2; }
.hero p { color: #aaa9a6; font-size: 1.05rem; margin: 0; }
.movie-card { background: #1b1c20; border: 1px solid #323338; border-radius: 16px; padding: 1rem; min-height: 150px; }
.movie-card h3 { margin: .2rem 0 .5rem; color:#fffaf2; }
.movie-meta { color:#aaa9a6; font-size:.88rem; line-height:1.7; }
div[data-testid="stMetric"] { background:#1b1c20; border:1px solid #323338; padding:1rem; border-radius:14px; }
div[data-testid="stMetricLabel"] { color:#aaa9a6; }
button[kind="primary"] { background:#d4a95f; color:#171717; border:0; }
button[kind="primary"]:hover { background:#e2bc7b; color:#171717; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="hero"><div class="eyebrow">FILMLOG · MOVIE JOURNAL</div><h1>영화를 보고,<br>마음을 읽다.</h1><p>영화와 감상평을 기록하고, 리뷰의 분위기를 함께 살펴보세요.</p></div>', unsafe_allow_html=True)

try:
    movies = api("GET", "/movies")
except ApiError as exc:
    show_error(exc)
    st.info("백엔드 API를 실행한 뒤 새로고침해 주세요.")
    st.stop()

movie_count = len(movies)
review_count = sum(item["review_count"] for item in movies)
scored = [item["average_rating"] for item in movies if item["average_rating"] is not None]
col1, col2, col3 = st.columns(3)
col1.metric("등록한 영화", f"{movie_count}편")
col2.metric("쌓인 리뷰", f"{review_count}개")
col3.metric("전체 평균", f"{sum(scored) / len(scored):.1f} / 5" if scored else "아직 없음")

tab_movies, tab_add, tab_review, tab_recent = st.tabs(["🎞️ 영화 목록", "＋ 영화 추가", "✍️ 리뷰 등록", "▤ 최근 리뷰"])

with tab_movies:
    st.subheader("내 영화 컬렉션")
    if not movies:
        st.info("첫 번째 영화를 등록해 컬렉션을 시작하세요.")
    else:
        cols = st.columns(3)
        for i, movie in enumerate(movies):
            with cols[i % 3]:
                with st.container(border=True):
                    if movie.get("poster_url"):
                        st.image(movie["poster_url"], use_container_width=True)
                    st.markdown(f"### {movie['title']}")
                    metadata = " · ".join(filter(None, [movie.get("release_date", ""), movie.get("genre", "")]))
                    st.caption(metadata or "상세 정보 없음")
                    st.caption(f"감독 {movie.get('director') or '미입력'}")
                    if movie.get("average_rating") is not None:
                        st.markdown(f"⭐ **{movie['average_rating']:.1f} / 5**　·　리뷰 {movie['review_count']}개")
                    else:
                        st.caption("아직 리뷰가 없습니다")
                    with st.expander("영화 정보 / 삭제"):
                        st.caption(f"영화 ID: {movie['id']}")
                        if st.button("영화 삭제", key=f"delete-movie-{movie['id']}"):
                            try:
                                api("DELETE", f"/movies/{movie['id']}")
                                st.success("영화와 연결된 리뷰를 삭제했습니다.")
                                st.rerun()
                            except ApiError as exc:
                                show_error(exc)

with tab_add:
    st.subheader("새 영화 기록")
    with st.form("movie-form", clear_on_submit=True):
        title = st.text_input("영화 제목 *", placeholder="예: 기생충")
        c1, c2 = st.columns(2)
        release_date = c1.date_input("개봉일", value=None, format="YYYY-MM-DD")
        director = c2.text_input("감독", placeholder="봉준호")
        genre = st.text_input("장르", placeholder="드라마, 스릴러")
        poster_url = st.text_input("포스터 이미지 URL", placeholder="https://...")
        submitted = st.form_submit_button("영화 추가", type="primary", use_container_width=True)
    if submitted:
        if not title.strip():
            st.warning("영화 제목을 입력해 주세요.")
        else:
            payload = {"title": title, "release_date": release_date.isoformat() if release_date else None,
                       "director": director or None, "genre": genre or None, "poster_url": poster_url or None}
            try:
                created = api("POST", "/movies", json=payload)
                st.success(f"‘{created['title']}’을(를) 등록했습니다.")
                st.rerun()
            except ApiError as exc:
                show_error(exc)

with tab_review:
    st.subheader("감상평 남기기")
    if not movies:
        st.info("먼저 영화 목록에 영화를 추가해 주세요.")
    else:
        with st.form("review-form", clear_on_submit=True):
            selected = st.selectbox("영화 선택", movies, format_func=lambda item: f"{item['title']} · ID {item['id']}")
            author = st.text_input("작성자 이름", placeholder="닉네임")
            content = st.text_area("리뷰 내용", placeholder="영화를 보고 든 생각을 남겨 보세요.", max_chars=5000, height=160)
            submitted_review = st.form_submit_button("리뷰 등록 및 감성 분석", type="primary", use_container_width=True)
        if submitted_review:
            if not author.strip() or len(content.strip()) < 2:
                st.warning("작성자와 두 글자 이상의 리뷰를 입력해 주세요.")
            else:
                with st.spinner("리뷰를 분석하고 저장하는 중…"):
                    try:
                        result = api("POST", "/reviews", json={"movie_id": selected["id"], "author": author, "content": content})
                        st.success(f"{result['sentiment_label']} 리뷰 · 감성 점수 {result['sentiment_score']:+.2f} · 신뢰도 {result['sentiment_confidence']:.0%}")
                        st.caption("감성 분석 결과는 참고용이며, 문맥·반어 표현에 따라 실제 감상과 다를 수 있습니다.")
                    except ApiError as exc:
                        show_error(exc)

with tab_recent:
    st.subheader("최근 리뷰")
    chosen_id = st.selectbox("영화 필터", [None] + movies, format_func=lambda item: "전체 영화" if item is None else item["title"], key="recent-filter")
    try:
        path = "/reviews?limit=10" + (f"&movie_id={chosen_id['id']}" if chosen_id else "")
        reviews = api("GET", path)
        if not reviews:
            st.info("아직 등록된 리뷰가 없습니다.")
        for review in reviews:
            with st.container(border=True):
                movie = next((m for m in movies if m["id"] == review["movie_id"]), None)
                label_color = "🟢" if review["sentiment_label"] == "긍정" else "🔴"
                date_text = datetime.fromisoformat(review["created_at"].replace("Z", "+00:00")).astimezone().strftime("%Y.%m.%d %H:%M")
                st.markdown(f"{label_color} **{movie['title'] if movie else '영화'}** · 영화 ID {review['movie_id']}　|　{date_text}　|　{review['author']}")
                st.write(review["content"])
                st.caption(f"감성: {review['sentiment_label']}　·　점수 {review['sentiment_score']:+.2f}　·　신뢰도 {review['sentiment_confidence']:.0%}")
                if st.button("리뷰 삭제", key=f"delete-review-{review['id']}"):
                    try:
                        api("DELETE", f"/reviews/{review['id']}")
                        st.rerun()
                    except ApiError as exc:
                        show_error(exc)
    except ApiError as exc:
        show_error(exc)
