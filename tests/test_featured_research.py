"""
Featured research - main landing page inline PDF viewer.

Guards ``get_cached_featured_research``: the home page block must only surface
posts that are published, public, marked ``is_featured`` and resolve to an
accessible PDF. Also checks the section renders with an inline iframe and that
the PDF is served inline.
"""

from datetime import datetime

from app import create_app
from app.extensions import db
from app.models import User, BlogPost
from app.utils.neon_cache import get_cached_featured_research

PDF_BYTES = b"%PDF-1.4\n%%EOF"


def _make_user() -> User:
    user = User.query.filter_by(email="featured-test@example.com").first()
    if not user:
        user = User(email="featured-test@example.com", full_name="Featured Tester",
                    is_active=True)
        user.set_password("x")
        db.session.add(user)
        db.session.commit()
    return user


def _make_post(user, slug, *, featured, status="published", with_pdf=True, title=None):
    post = BlogPost(
        title=title or slug,
        slug=slug,
        content="<p>Featured research body.</p>",
        excerpt="Featured research excerpt.",
        author_id=user.id,
        is_public=True,
        is_featured=featured,
        status=status,
        published_at=datetime.utcnow() if status == "published" else None,
        pdf_binary=PDF_BYTES if with_pdf else None,
        pdf_content_type="application/pdf" if with_pdf else None,
    )
    db.session.add(post)
    return post


def _cleanup():
    for post in BlogPost.query.filter(BlogPost.slug.like("featured-test-%")).all():
        db.session.delete(post)
    db.session.commit()


def test_only_featured_published_pdf_posts_are_returned():
    app = create_app()
    with app.app_context():
        _cleanup()
        user = _make_user()
        _make_post(user, "featured-test-qualifies", featured=True, with_pdf=True)
        _make_post(user, "featured-test-no-pdf", featured=True, with_pdf=False)
        _make_post(user, "featured-test-not-featured", featured=False, with_pdf=True)
        _make_post(user, "featured-test-draft", featured=True, status="draft", with_pdf=True)
        db.session.commit()

        try:
            posts = get_cached_featured_research(limit=6, force_refresh=True)
            slugs = {p.slug for p in posts}

            assert "featured-test-qualifies" in slugs
            assert not ({"featured-test-no-pdf", "featured-test-not-featured",
                         "featured-test-draft"} & slugs)

            # PDF fields must survive serialization for the template.
            qualifying = next(p for p in posts if p.slug == "featured-test-qualifies")
            assert qualifying.is_pdf_post is True
            assert qualifying.pdf_url
        finally:
            _cleanup()


def test_home_page_renders_inline_viewer_and_serves_pdf():
    app = create_app()
    with app.app_context():
        _cleanup()
        user = _make_user()
        post = _make_post(user, "featured-test-home", featured=True, with_pdf=True)
        db.session.commit()
        post_id = post.id

        try:
            client = app.test_client()

            html = client.get("/").get_data(as_text=True)
            assert 'id="research"' in html
            assert 'id="featuredResearchFrame"' in html
            assert 'class="research-viewer"' in html
            assert "function selectFeaturedResearch" in html
            # the old blog-card research section is gone
            assert "From Our Research" not in html

            pdf = client.get(f"/blog/pdf/{post_id}")
            assert pdf.status_code == 200
            assert pdf.headers["Content-Type"] == "application/pdf"
            assert "inline" in pdf.headers.get("Content-Disposition", "")
        finally:
            _cleanup()
