"""
Pure UI building blocks. Save persists per-user via local_client.save_
bookmark() once someone's signed in (local_auth.current_user()), falling
back to session-only save for a logged-out/guest view --- see that
function's docstring for the full per-user-vs-session split.

Combined-repo addition: onboarding_carousel() / brand_image_data_uri() /
hub_banner() below are new in this round, added alongside the existing
building blocks rather than in a separate module --- this file was
already "shared widgets" per README.md's project layout, and the brand
photos are used by pages/0_Auth.py, pages/1_Home.py, and
pages/7_KIU_Hub.py, so a shared home for them (with the shared image-
loading cache) avoids three copies of the same base64-encoding logic.
"""
import base64
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

import local_auth
from local_client import save_bookmark, record_resource_opened

ONBOARDING_DIR = Path(__file__).parent / "assets" / "onboarding"

FILE_TYPE_STYLE = {
    "video": {"color": "#DC2626", "label": "VIDEO", "icon": "▶️"},  # red, per request --- notes/docs already get their own distinct color below; video gets red the same way
    "ppt":  {"color": "#F97316", "label": "PPT",  "icon": "📊"},
    "pdf":  {"color": "#EF4444", "label": "PDF",  "icon": "📄"},
    "note": {"color": "#3B82F6", "label": "NOTE", "icon": "📝"},
    "doc":  {"color": "#3B82F6", "label": "DOC",  "icon": "📃"},
}
DEFAULT_STYLE = {"color": "#6B7280", "label": "FILE", "icon": "📎"}

# Combined-repo addition: per-tile background colors for the "My Active
# Courses" grid (course_unit_tile() below) --- a deliberately different
# palette from FILE_TYPE_STYLE above rather than reusing those colors,
# so a colored course tile never gets misread as meaning the same thing
# a colored file-type chip does elsewhere in the app (red already means
# "video", blue already means "note/doc", etc.). All eight are roughly
# the same depth/saturation as the FILE_TYPE_STYLE colors specifically
# so white text sits on them with the same contrast those chips already
# rely on.
COURSE_TILE_PALETTE = [
    "#E85D2C",  # brand orange
    "#2563EB",  # blue
    "#7C3AED",  # violet
    "#0D9488",  # teal
    "#DB2777",  # rose
    "#D97706",  # amber
    "#059669",  # emerald
    "#4F46E5",  # indigo
]


def inject_base_css():
    st.markdown(
        """
        <style>
        div[data-testid="stAppViewContainer"] > .main { padding-bottom: 5.5rem; }
        .card {
            border: 1px solid #E5E7EB;
            border-radius: 12px;
            padding: 0.9rem 1rem;
            margin-bottom: 0.6rem;
            background: #FFFFFF;
        }
        .card-title { font-weight: 600; font-size: 0.98rem; margin-bottom: 0.15rem; }
        .card-meta { color: #6B7280; font-size: 0.8rem; }
        .type-chip {
            display: inline-block;
            font-size: 0.7rem;
            font-weight: 700;
            padding: 0.1rem 0.5rem;
            border-radius: 6px;
            color: white;
            margin-right: 0.4rem;
        }
        .course-chip {
            display: inline-block;
            border: 1px solid #E85D2C;
            color: #E85D2C;
            border-radius: 999px;
            padding: 0.3rem 0.9rem;
            margin-right: 0.5rem;
            font-weight: 600;
            font-size: 0.85rem;
        }
        .switch-wordmark {
            font-weight: 800;
            letter-spacing: -0.02em;
            color: #E85D2C;
        }
        .switch-wordmark .dot { color: #1A1A2E; }
        .st-key-bottom_nav {
            position: fixed;
            bottom: 0; left: 0; right: 0;
            background: #FFFFFF;
            border-top: 1px solid #E5E7EB;
            padding: 0.4rem 0.5rem;
            z-index: 999;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def _all_onboarding_data_uris() -> list[str]:
    """Base64 data-URIs for every image in assets/onboarding/, read once
    and cached for the running app's lifetime --- these are static
    bundled assets that never change at runtime, so re-reading and
    re-encoding them from disk on every Streamlit rerun (which happens
    on every button click anywhere on the page) would be pure waste.
    Embedding as data URIs (rather than plain file paths) is what makes
    onboarding_carousel() below work inside components.html()'s iframe
    without depending on how Streamlit happens to serve static files in
    a given environment --- local run and Streamlit Community Cloud have
    both been known to differ there, and a data URI sidesteps the
    question entirely. Returns [] (not an error) if the folder is
    missing or empty, so a repo checked out without the assets/
    directory degrades to "no carousel" rather than a crash."""
    if not ONBOARDING_DIR.exists():
        return []
    uris = []
    for path in sorted(ONBOARDING_DIR.glob("*.jpg")):
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        uris.append(f"data:image/jpeg;base64,{encoded}")
    return uris


@st.cache_data(show_spinner=False)
def brand_image_data_uri(filename: str) -> str:
    """Same caching/data-URI reasoning as _all_onboarding_data_uris()
    above, for call sites that want exactly one named brand photo
    (hub_banner() below, and pages/7_KIU_Hub.py's header) rather than
    the full set. Returns "" if the file doesn't exist so callers can
    fall back to a plain color instead of a broken image."""
    path = ONBOARDING_DIR / filename
    if not path.exists():
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def onboarding_carousel(height: int = 230):
    """Auto-advancing, swipeable strip of the brand photos for the sign-
    up/login screen --- the literal "dynamic, swiping from one to the
    next" ask. Rendered via components.html() (a real sandboxed iframe)
    rather than st.markdown(unsafe_allow_html=True): the swipe/autoplay
    behavior needs actual <script> execution, and Streamlit's markdown
    renderer doesn't reliably run injected scripts the way a genuine
    iframe does --- every other custom-HTML block in this file
    (youtube_embed, drive_doc_embed, resource cards) is static markup
    with no JS, which is exactly why those stayed on st.markdown while
    this one didn't.

    The swipe gesture itself is plain CSS (scroll-snap on a horizontally
    scrolling flex row) --- that part works with no JS at all and is
    what makes a manual swipe feel native on a touchscreen. The JS layer
    on top only adds autoplay (advance every 3.2s) and the dot
    indicator, and pauses autoplay while a touch/mouse interaction is in
    progress so it never fights a swipe the person is mid-gesture on.

    Renders nothing (not a broken placeholder) if assets/onboarding/ is
    empty --- see _all_onboarding_data_uris()."""
    images = _all_onboarding_data_uris()
    if not images:
        return

    slides_html = "".join(
        f'<div class="swc-slide"><img src="{src}" alt="Switch"></div>' for src in images
    )
    dots_html = "".join(
        f'<div class="swc-dot{" active" if i == 0 else ""}"></div>' for i in range(len(images))
    )

    html = f"""
    <style>
      * {{ box-sizing: border-box; }}
      body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
      .swc-track {{
        display: flex;
        overflow-x: auto;
        scroll-snap-type: x mandatory;
        -webkit-overflow-scrolling: touch;
        border-radius: 18px;
        scrollbar-width: none;
        -ms-overflow-style: none;
      }}
      .swc-track::-webkit-scrollbar {{ display: none; }}
      .swc-slide {{
        flex: 0 0 100%;
        scroll-snap-align: center;
      }}
      .swc-slide img {{
        width: 100%;
        height: {height}px;
        object-fit: cover;
        display: block;
      }}
      .swc-dots {{
        display: flex;
        justify-content: center;
        gap: 6px;
        margin-top: 10px;
      }}
      .swc-dot {{
        width: 7px; height: 7px; border-radius: 50%;
        background: #E5D9CE;
        transition: background 0.25s ease, transform 0.25s ease;
      }}
      .swc-dot.active {{ background: #E85D2C; transform: scale(1.3); }}
    </style>
    <div class="swc-track" id="swcTrack">{slides_html}</div>
    <div class="swc-dots" id="swcDots">{dots_html}</div>
    <script>
    (function() {{
      var track = document.getElementById('swcTrack');
      var dots = document.getElementById('swcDots').children;
      var n = track.children.length;
      var idx = 0;
      var interacting = false;
      var resumeTimer = null;

      function updateDots() {{
        for (var i = 0; i < n; i++) {{
          dots[i].className = 'swc-dot' + (i === idx ? ' active' : '');
        }}
      }}
      function goTo(i) {{
        idx = (i + n) % n;
        track.scrollTo({{ left: idx * track.clientWidth, behavior: 'smooth' }});
        updateDots();
      }}
      var timer = setInterval(function() {{
        if (!interacting) goTo(idx + 1);
      }}, 3200);

      track.addEventListener('scroll', function() {{
        if (track.clientWidth === 0) return;
        var i = Math.round(track.scrollLeft / track.clientWidth);
        if (i !== idx) {{ idx = i; updateDots(); }}
      }}, {{ passive: true }});

      ['touchstart', 'mousedown'].forEach(function(evt) {{
        track.addEventListener(evt, function() {{
          interacting = true;
          clearTimeout(resumeTimer);
        }}, {{ passive: true }});
      }});
      ['touchend', 'mouseup'].forEach(function(evt) {{
        track.addEventListener(evt, function() {{
          resumeTimer = setTimeout(function() {{ interacting = false; }}, 2600);
        }}, {{ passive: true }});
      }});
    }})();
    </script>
    """
    components.html(html, height=height + 26)


def hub_banner():
    """Colorful entry-point card for the KIU Resource Hub, shown near the
    top of Home --- the "access the second app from the main app's UX"
    ask, made into an actual visible, branded doorway rather than a bare
    link. Image + gradient is static markup (st.markdown is fine here,
    unlike onboarding_carousel --- no JS involved), followed by a real
    st.button for the actual navigation: the same card-renders-then-a-
    real-button-underneath split resource_card() and course_unit_tile()
    above already use, not a new pattern invented for just this card.
    Falls back to a plain gradient (no broken image) if the named photo
    is missing --- see brand_image_data_uri()."""
    image = brand_image_data_uri("switch-04.jpg")
    if image:
        background = (
            f"background-image: linear-gradient(180deg, rgba(26,26,46,0.05) 35%, "
            f"rgba(26,26,46,0.82) 100%), url('{image}'); background-size: cover; "
            f"background-position: center;"
        )
    else:
        background = "background: linear-gradient(135deg, #1F6F5C, #E85D2C);"

    st.markdown(
        f"""
        <div style="border-radius:16px; overflow:hidden; {background}
                    padding:1.4rem 1.1rem 1rem; margin-bottom:0.6rem; min-height:132px;
                    display:flex; flex-direction:column; justify-content:flex-end;">
            <div style="color:#FFFFFF; font-weight:700; font-size:1.05rem;">🎓 KIU Resource Hub</div>
            <div style="color:#F3F1EC; font-size:0.85rem; margin-top:0.15rem;">
                Hostels, jobs &amp; scholarships for KIU students
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Explore the Hub →", key="hub_banner_cta", use_container_width=True):
        st.switch_page("pages/7_KIU_Hub.py")


def wordmark(size: str = "1.4rem"):
    """Renders the 'switch.' wordmark --- lowercase, bold, trailing dot in ink not orange."""
    st.markdown(
        f'<div class="switch-wordmark" style="font-size:{size};">switch<span class="dot">.</span></div>',
        unsafe_allow_html=True,
    )


def file_type_chip(file_type: str) -> str:
    style = FILE_TYPE_STYLE.get(file_type, DEFAULT_STYLE)
    return f'<span class="type-chip" style="background:{style["color"]}">{style["icon"]} {style["label"]}</span>'


def resource_card(resource: dict, key_prefix: str):
    """Renders one feed/list card. Returns the button-click routing signal, if any."""
    style = FILE_TYPE_STYLE.get(resource.get("file_type"), DEFAULT_STYLE)
    with st.container():
        st.markdown(
            f"""
            <div class="card" style="border-left: 4px solid {style['color']};">
                <div>{file_type_chip(resource.get('file_type', ''))}
                    <span class="card-meta">{resource.get('course_code', '')}</span>
                </div>
                <div class="card-title">{resource.get('title', 'Untitled')}</div>
                <div class="card-meta">
                    {resource.get('uploader', '')}{' · ' if resource.get('uploader') else ''}{resource.get('uploaded_at', '')}
                    {' · ▲ ' + str(resource['upvotes']) if 'upvotes' in resource else ''}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        cols = st.columns([1, 1, 1])
        open_clicked = cols[0].button("Open", key=f"{key_prefix}_open_{resource['id']}", use_container_width=True)
        save_clicked = cols[1].button("🔖 Save", key=f"{key_prefix}_save_{resource['id']}", use_container_width=True)
        share_clicked = cols[2].button("🔗 Share", key=f"{key_prefix}_share_{resource['id']}", use_container_width=True)

        if open_clicked:
            st.session_state["active_resource_id"] = resource["id"]
            st.session_state["_last_opened_resource"] = resource
            st.switch_page("pages/6_Viewer.py")
        if save_clicked:
            user = local_auth.current_user()
            save_bookmark(resource, student_id=user["user_id"] if user else "demo-student")
            st.toast(f"Saved \"{resource.get('title')}\"")
        if share_clicked:
            st.toast("Share link copied (placeholder --- wire to real deep-link generation later)")


def youtube_embed(video_id: str, height: int = 220):
    """Renders an actual playable YouTube iframe embed (not just a link
    or a thumbnail-with-click-through) --- this is the literal 'embed
    the videos' ask. Wrapped in a rounded container matching .card's
    styling so it sits visually consistent with the rest of the UI
    rather than looking like a bare unstyled iframe."""
    st.markdown(
        f"""
        <div style="border-radius:12px; overflow:hidden; border:1px solid #E5E7EB;">
            <iframe width="100%" height="{height}"
                src="https://www.youtube.com/embed/{video_id}"
                title="YouTube video player"
                frameborder="0"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowfullscreen>
            </iframe>
        </div>
        """,
        unsafe_allow_html=True,
    )


def drive_doc_embed(embed_url: str, height: int = 400):
    """Round 3: renders a Google Docs/Sheets/Slides/Drive-file inline
    preview via an iframe pointed at Google's own /preview (or /embed,
    for Slides) address --- the note/doc (drive_notes/drive_questions)
    equivalent of youtube_embed() above, same wrapping/styling
    treatment. `embed_url` is the already-built address from
    tree_store.drive_embed_url(); this function only renders it,
    matching youtube_embed()'s own split between building the address
    (tree_store) and rendering it (here).

    Google's /preview endpoint renders its own "you need access" page
    inside the iframe for a document that isn't shared "Anyone with
    the link" --- there's no way to tell that apart from a real
    document loading correctly from here, since the iframe's contents
    are cross-origin. That's why the Viewer (pages/6_Viewer.py) always
    shows a direct Open-in-Google-Docs link alongside this embed, not
    only when this is judged to have failed."""
    st.markdown(
        f"""
        <div style="border-radius:12px; overflow:hidden; border:1px solid #E5E7EB;">
            <iframe src="{embed_url}" width="100%" height="{height}" frameborder="0"></iframe>
        </div>
        """,
        unsafe_allow_html=True,
    )


def video_resource_card(resource: dict, key_prefix: str):
    """Like resource_card(), but for file_type == 'video': renders the
    actual playable embed inline (via youtube_embed()) instead of an
    Open button that navigates away, since the point of embedding is
    not having to leave the card to watch. Save/Share stay as buttons
    below the embed --- Open is dropped since there's nothing further
    for a click-through 'Open' to do once the video is already playing
    right there."""
    style = FILE_TYPE_STYLE.get("video", DEFAULT_STYLE)
    video_id = resource.get("youtube_video_id")
    with st.container():
        st.markdown(
            f"""
            <div class="card" style="border-left: 4px solid {style['color']}; padding-bottom:0.5rem;">
                <div>{file_type_chip('video')}
                    <span class="card-meta">{resource.get('course_code', '')}</span>
                </div>
                <div class="card-title">{resource.get('title', 'Untitled')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if video_id:
            youtube_embed(video_id)
        else:
            # A youtube-kind link whose url didn't match the expected
            # pattern (see tree_store.youtube_video_id) --- fall back to
            # a plain link rather than an iframe pointed at nothing.
            st.caption(f"Couldn't embed this video. [Open on YouTube]({resource.get('url', '')})")

        cols = st.columns([1, 1])
        save_clicked = cols[0].button("🔖 Save", key=f"{key_prefix}_save_{resource['id']}", use_container_width=True)
        share_clicked = cols[1].button("🔗 Share", key=f"{key_prefix}_share_{resource['id']}", use_container_width=True)
        if save_clicked:
            user = local_auth.current_user()
            save_bookmark(resource, student_id=user["user_id"] if user else "demo-student")
            st.toast(f"Saved \"{resource.get('title')}\"")
        if share_clicked:
            st.toast("Share link copied (placeholder --- wire to real deep-link generation later)")

        # Recorded here (not just from the Viewer page) because embedded
        # videos are now watched in-place and may never route through
        # 6_Viewer.py at all --- history would silently miss every
        # embedded view otherwise. Guarded to fire once per Streamlit
        # session per resource: Streamlit reruns this whole page on ANY
        # button click anywhere on it (e.g. clicking Save on a
        # different card), and without this guard every such rerun
        # would re-record this video as "just opened" even though the
        # person didn't touch it that time --- reaching Course Detail
        # at all already required an explicit navigation click, so
        # that's the real "opened" signal; re-renders after that within
        # the same session aren't.
        if video_id:
            recorded_key = f"_history_recorded_{resource['id']}"
            if not st.session_state.get(recorded_key):
                user = local_auth.current_user()
                if user:
                    record_resource_opened(user["user_id"], resource)
                st.session_state[recorded_key] = True


def bottom_nav(active: str):
    """Renders the fixed bottom tab bar. `active` highlights the current tab.

    Round 3 fix: this used to open the wrapping div with one
    st.markdown() call, run st.columns()/st.button() in between, then
    close it with a second, separate st.markdown("</div>") call.
    Streamlit renders each st.markdown() call as its own self-contained
    element on the page --- nothing rendered between two separate calls
    actually ends up nested inside a div opened by an earlier one. In
    practice that meant the opening call produced an empty, self-closed
    box; the columns/buttons rendered afterward, outside it and
    unstyled by .bottom-nav's fixed-position/background/border rules;
    and the second call's closing tag was left dangling with nothing
    to close, its own orphaned element on the page.

    Fixed with st.container(key=...), which Streamlit (1.39+; see the
    requirements.txt bump) renders as a real wrapping element carrying
    an .st-key-<key> class --- so the columns/buttons below genuinely
    end up inside the styled container this time, in one call instead
    of two. See inject_base_css() above for the matching
    .st-key-bottom_nav rule (renamed from the old .bottom-nav, since
    the class is no longer applied by hand).

    Combined-repo addition: a fifth "Hub" tab (KIU Resource Hub) sits
    between My Courses and Upload --- center position, on the theory
    that a bottom nav's middle slot is the one that draws the eye first
    on a row of otherwise-equal-weight icons, which suits a newly-added
    destination the rest of this round is trying to make genuinely
    discoverable. This is a judgment call, not a measured one (no real
    device to test tap targets against five columns instead of four ---
    see the handoff's Testing/Still Open notes); worth revisiting if
    five columns ever reads as cramped on a narrow phone."""
    with st.container(key="bottom_nav"):
        cols = st.columns(5)
        tabs = [
            ("Home", "🏠", "pages/1_Home.py"),
            ("My Courses", "📚", "pages/2_My_Courses.py"),
            ("Hub", "🎓", "pages/7_KIU_Hub.py"),
            ("Upload", "⬆️", "pages/4_Upload.py"),
            ("Saved", "🔖", "pages/5_Saved.py"),
        ]
        for col, (label, icon, page) in zip(cols, tabs):
            is_active = label == active
            display = f"**{icon} {label}**" if is_active else f"{icon} {label}"
            if col.button(display, key=f"nav_{label}", use_container_width=True):
                st.switch_page(page)


def course_unit_tile(course: dict, key_prefix: str, index: int = 0, target_page: str = "pages/3_Course_Detail.py"):
    """A single course-unit tile for the 'My Active Courses' grid. Uses a
    solid-color card (COURSE_TILE_PALETTE below) rather than the plain
    white .card shell every other card in the app uses --- the explicit
    "colourful tiles" ask, and a deliberate one-off departure from the
    shared .card look for exactly this grid, not a change to card styling
    generally. White-on-color text follows the same pattern already
    established by the file-type chips above (FILE_TYPE_STYLE + .type-
    chip: colored background, white text), so this isn't a new visual
    language for the app, just a bigger application of one it already
    uses.

    Color is chosen by `index` (the course's position in its semester's
    list, passed by the caller's enumerate() loop) rather than hashed
    from the course id/name: Python's string hash() is randomized per
    process by default (PYTHONHASHSEED), so a hash-based pick would
    silently reshuffle every color on every app restart, while position-
    based picking is fully deterministic as long as the semester's
    course order doesn't change --- which it doesn't, since that order
    comes from each node's stored sort_order, not from render-time
    chance.

    Still uses the existing .course-chip-less plain pill for the code
    label, just recolored per-tile to sit on the background rather than
    the fixed orange-on-white version elsewhere; .course-chip itself
    (orange outline, white fill) is left as-is for any future use that
    wants the original look. Returns True if the tile's button was
    clicked this run, same hand-back-to-caller pattern resource_card()
    etc. use rather than navigating internally in every case."""
    color = COURSE_TILE_PALETTE[index % len(COURSE_TILE_PALETTE)]
    with st.container():
        st.markdown(
            f"""
            <div style="background:{color}; border-radius:14px; text-align:center;
                        padding:1.2rem 0.8rem 1rem; box-shadow:0 1px 3px rgba(0,0,0,0.14);">
                <div style="display:inline-block; background:rgba(255,255,255,0.24); color:#FFFFFF;
                            border-radius:999px; padding:0.25rem 0.8rem; font-weight:700;
                            font-size:0.75rem; letter-spacing:0.02em;">{course.get('code', 'COURSE')}</div>
                <div style="color:#FFFFFF; font-weight:700; font-size:1rem; margin-top:0.55rem;
                            line-height:1.25;">{course.get('name', 'Untitled')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        clicked = st.button("Open", key=f"{key_prefix}_tile_{course['id']}", use_container_width=True)
    if clicked:
        st.session_state["active_course"] = course
        st.switch_page(target_page)
    return clicked
