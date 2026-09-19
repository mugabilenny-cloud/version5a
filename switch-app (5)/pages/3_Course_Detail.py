import streamlit as st

from local_client import fetch_children_as_resources
from ui_components import inject_base_css, resource_card, video_resource_card, bottom_nav

st.set_page_config(page_title="Course | Switch", page_icon="🟠", layout="centered", initial_sidebar_state="collapsed")
inject_base_css()

course = st.session_state.get("active_course", {"code": "---", "name": "Unknown course"})

if st.button("← Back"):
    st.switch_page("pages/1_Home.py")

st.markdown(f"### {course.get('code')}")
st.caption(course.get("name", ""))
st.divider()

# The real tree is 8 levels deep --- a node here may hold more nodes
# (keep drilling) or, at the bottom, real links (show them). The old
# version assumed every course had a flat resource list one click away;
# that assumption doesn't hold against a real multi-level tree, so this
# branches instead of flattening.
kind, items = fetch_children_as_resources(course.get("id"))

if kind == "nodes":
    # Folder-level (non-leaf) rendering --- unchanged. Rule #6 of the
    # handoff doc's agent instructions explicitly scopes gap #3's fix to
    # the leaf/links case only; this branch is not part of that gap.
    st.markdown("#### Browse further")
    for node in items:
        with st.container():
            st.markdown(
                f"""<div class="card"><div class="card-title">{node['code']} --- {node['name']}</div></div>""",
                unsafe_allow_html=True,
            )
            if st.button("Open", key=f"drill_{node['id']}", use_container_width=True):
                st.session_state["active_course"] = node
                st.rerun()
else:
    # gap #3 fix: `items` is now a list of (title, [resource, ...]) groups
    # from fetch_children_as_resources()'s updated leaf branch, instead of
    # one flat list --- this is what actually surfaces the 15 distinct
    # topics (Epilepsy 2, Meningitis, Stroke, etc.) that were previously
    # invisible because every link at this leaf shared one node_id. Each
    # group gets its own labeled sub-header; within a group, a video-kind
    # resource renders as a playable embed (video_resource_card) rather
    # than a plain link-out card, same dispatch-by-file_type pattern used
    # everywhere else video/non-video resources are rendered together.
    st.markdown("#### Resources")
    if not items:
        st.info("No links added here yet.")
    for title, resources in items:
        st.markdown(f"##### {title if title else 'Untitled'}")
        for resource in resources:
            if resource.get("file_type") == "video":
                video_resource_card(resource, key_prefix="coursedetail")
            else:
                resource_card(resource, key_prefix="coursedetail")

st.write("")
bottom_nav(active="My Courses")
