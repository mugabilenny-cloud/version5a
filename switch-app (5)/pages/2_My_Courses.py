import streamlit as st

import local_auth
from local_client import fetch_active_courses
from ui_components import inject_base_css, bottom_nav, wordmark

st.set_page_config(page_title="My Courses | Switch", page_icon="🟠", layout="centered", initial_sidebar_state="collapsed")
inject_base_css()

wordmark(size="1.1rem")
st.markdown("### My Courses")
st.caption("Browse into your course tree.")

# gap #2 fix: same missing-student_id problem as Home (gap #1) --- see
# that page's comment for the full rationale. No other change to this
# page's layout/cards; gap #2's text scopes this fix to the missing
# argument only.
user = local_auth.current_user()
student_id = user["user_id"] if user else "demo-student"
courses = fetch_active_courses(student_id=student_id)
for course in courses:
    count = course.get('resource_count')
    count_label = f"{count} resources" if count is not None else "Tap to browse"
    with st.container():
        st.markdown(
            f"""
            <div class="card">
                <div class="card-title">{course['code']} --- {course['name']}</div>
                <div class="card-meta">{count_label}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("View resources", key=f"mycourse_{course['id']}", use_container_width=True):
            st.session_state["active_course"] = course
            st.switch_page("pages/3_Course_Detail.py")

st.write("")
bottom_nav(active="My Courses")
