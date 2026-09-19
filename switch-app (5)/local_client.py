"""
Local data layer --- same nodes/links shape and the same function names/
signatures the six-screen UX already calls, but backed by data/tree.json
on disk instead of a live Supabase project over HTTP.

This file is a drop-in replacement for supabase_client.py: every public
function below has the identical name, signature, and return shape as
its counterpart there (see that file's docstrings for the full
rationale on each shim). ui_components.py and pages/*.py import from
here unchanged in spirit --- only the `from supabase_client import ...`
lines become `from local_client import ...`; nothing about how those
files CALL these functions changes.

What's genuinely different, because there's no live database or network:
  - No RPC calls, no requests library, no SUPABASE_URL/ANON_KEY.
  - Ads: the real schema handled these server-side via
    fn_get_ads_for_device. There is no ads table in this local file, so
    fetch_feed() returns an empty list (the Home screen already hides
    that section when empty).
  - device_token/register_device are legacy from the anonymous-only
    build and are now superseded by local_auth.py's session tokens for
    anything identity-related; they're kept only because app.py's
    bootstrap sequence still calls them before the auth gate runs (see
    app.py) --- register_device remains a no-op.
  - fetch_active_courses(), fetch_recently_viewed(), fetch_saved(), and
    save_bookmark() are now genuinely per-user (via local_auth's
    user_id and local_history.py), not session- or device-scoped. This
    is a real behavior change from the previous build, made because
    real accounts now exist: leaving Saved as session-only while
    History became durable would mean the same save silently surviving
    a closed tab in one section and vanishing in the other, which is
    an inconsistent product, not a deliberate design choice. All four
    now take a real user_id (still defaulting to "demo-student" for
    any call site that hasn't been updated to pass one, so nothing
    call-site-side breaks by omission) and return nothing meaningful
    for that default guest id beyond an empty state.
  - fn_search_tree's server-side search is reimplemented in
    tree_store.py's search(), extended to be hierarchy- and
    resource-kind-aware rather than a flat substring scan (see that
    module's docstring for the full rationale).
"""
import uuid
from pathlib import Path
from typing import Optional

import streamlit as st

import local_history
import local_saved
from tree_store import get_store

# ---------------------------------------------------------------------------
# Device identity (legacy --- see module docstring)
# ---------------------------------------------------------------------------

def get_or_create_device_token() -> str:
    params = st.query_params
    token = params.get("device")
    if not token:
        token = str(uuid.uuid4())
        st.query_params["device"] = token
    return token


def register_device(device_token: str, home_node_id: Optional[str] = None):
    """No-op locally --- there's no server-side device table to register
    against. Kept as a function (rather than removed) so app.py's call
    site needs no change."""
    return None


# ---------------------------------------------------------------------------
# Shims matching the ORIGINAL app's exact function names/signatures.
# ---------------------------------------------------------------------------

def fetch_active_courses(student_id: str = "demo-student"):
    """Course-unit tiles for the signed-in user's chosen semester (see
    local_auth.py --- semester is picked once at signup). Falls back to
    the tree roots (the pre-auth behavior) only when there's no real
    user_id, no stored semester, or the stored semester path doesn't
    resolve to a real node (e.g. data/tree.json was re-imported from a
    spreadsheet that no longer has that exact Year/Semester path) ---
    an unresolvable semester should degrade to "show something
    reasonable", never to a blank Home screen."""
    store = get_store()
    home_node_id = st.session_state.get("home_node_id")
    if home_node_id:
        nodes = store.children_of(home_node_id)
        return [store.node_to_course_shape(n) for n in nodes]

    semester_path = None
    if student_id and student_id != "demo-student":
        import local_auth
        user = local_auth.get_user_by_id(student_id)
        if user:
            semester_path = user.get("semester")

    if semester_path:
        semester_node = store.find_node_by_path_label(semester_path)
        if semester_node:
            nodes = store.children_of(semester_node["id"])
            if nodes:
                return [store.node_to_course_shape(n) for n in nodes]

    return [store.node_to_course_shape(n) for n in store.roots()]


def fetch_recently_viewed(student_id: str = "demo-student"):
    """Real per-user history via local_history.py, once a real user_id
    exists. The demo-student default returns empty --- same honest-empty
    fallback the pre-auth build used, now only hit by the logged-out/
    guest path rather than always."""
    if not student_id or student_id == "demo-student":
        return []
    return local_history.recent_for_user(student_id, limit=5)


def record_resource_opened(student_id: str, resource: dict):
    """Called from the Viewer page when a resource is actually opened
    (not on card render/hover) --- see local_history.py's
    record_opened() docstring for why that distinction matters."""
    if not student_id or student_id == "demo-student":
        return
    local_history.record_opened(student_id, resource)


def fetch_feed(department: Optional[str] = None):
    """No ads table exists in the local store, so this is an empty feed.
    See module docstring."""
    return []


def fetch_saved(student_id: str = "demo-student"):
    """Per-user saved list. See module docstring for why this moved off
    session state."""
    if not student_id or student_id == "demo-student":
        return st.session_state.get("_session_bookmarks", [])
    return local_saved.saved_for_user(student_id)


def save_bookmark(resource: dict, student_id: str = "demo-student"):
    """Per-user save. See module docstring. student_id is optional/
    keyword-compatible so existing call sites (ui_components.py's
    resource_card, pages/6_Viewer.py) that call save_bookmark(resource)
    positionally still work unchanged --- they're updated in this same
    change to pass the real signed-in id, but the default keeps the
    function from breaking if any call site is missed."""
    if not student_id or student_id == "demo-student":
        saved = st.session_state.get("_session_bookmarks", [])
        if not any(r["id"] == resource["id"] for r in saved):
            saved.append(resource)
        st.session_state["_session_bookmarks"] = saved
        return
    local_saved.save_for_user(student_id, resource)


def fetch_resource(resource_id: str):
    """Same fallback order as before: check session state buckets first
    (covers the ad-feed and the guest/session-only Saved path), then the
    local node/link store directly."""
    for bucket_key in ("_last_opened_resource", "_session_bookmarks"):
        bucket = st.session_state.get(bucket_key)
        if isinstance(bucket, dict) and bucket.get("id") == resource_id:
            return bucket
        if isinstance(bucket, list):
            for r in bucket:
                if r["id"] == resource_id:
                    return r

    store = get_store()
    link = store.link_by_id(resource_id)
    if link:
        node = store.node_by_id(link["node_id"])
        node_name = node["name"] if node else ""
        return store.link_to_resource_shape(link, node_name)

    return {"id": resource_id, "title": "Resource", "course_code": "---", "file_type": "link"}


def search_courses(query: str):
    """Node hits AND link hits, both carrying the hierarchy-aware tags
    TreeStore.search() already computes (matched_level on nodes,
    matched_in on links) --- gap #6 of the handoff doc: this function
    used to discard link hits and the matched_level field entirely,
    even though the search engine underneath it already produced them.
    Node shape stays {id, code, name, matched_level} (code is still the
    truncated path label, same as before, for anything already relying
    on that field); link hits are returned via tree_store's own
    link_to_resource_shape() so a search result and a normal resource
    card use the identical shape --- no new shape invented for this."""
    if not query:
        return [], []
    store = get_store()
    node_hits, link_hits = store.search(query)
    node_results = [
        {
            "id": n["id"],
            "code": store.node_path_label(n)[:12],
            "name": n.get("name", ""),
            "matched_level": n.get("matched_level", "node"),
        }
        for n in node_hits
    ]
    link_results = []
    for l in link_hits:
        parent_node = store.node_by_id(l.get("node_id"))
        parent_name = parent_node.get("name", "") if parent_node else ""
        shaped = store.link_to_resource_shape(l, parent_name)
        shaped["matched_in"] = l.get("matched_in")
        link_results.append(shaped)
    return node_results, link_results


def search_tree(query: str):
    """Full search --- both node and link hits --- for screens that want
    the complete picture, mirroring what fn_search_tree exposed."""
    if not query:
        return [], []
    return get_store().search(query)


def fetch_children_as_resources(node_id: str):
    """Same branch-on-folder-vs-leaf contract as the Supabase version.

    Leaf branch updated (gap #3 of the handoff doc): now returns
    grouped-by-title link groups instead of a flat list, using
    links_for_node_grouped() (built and tested previously but never
    wired up until now) --- this is what actually fixes the "Class"
    leaf-collapse problem (see tree_store.py's module docstring) at
    the page level. Return shape for the "links" kind changes from a
    flat list of resource dicts to a list of (title, [resource, ...])
    tuples, since that's what pages/3_Course_Detail.py needs to render
    labeled sub-sections; the "nodes" (folder) branch is untouched ---
    rule #6 of the handoff doc's agent instructions explicitly scopes
    this fix to the leaf/links case only."""
    store = get_store()
    children = store.children_of(node_id)
    if children:
        return "nodes", [store.node_to_course_shape(n) for n in children]

    node = store.node_by_id(node_id)
    node_name = node.get("name", "") if node else ""
    grouped = store.links_for_node_grouped(node_id)
    groups = [
        (title, [store.link_to_resource_shape(link, node_name) for link in links])
        for title, links in grouped
    ]
    return "links", groups
