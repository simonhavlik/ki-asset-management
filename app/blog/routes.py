"""
Blog routes for KI Asset Management.

This module handles all blog-related functionality including:
- Public blog listing and article viewing (SEO optimized)
- Member blog editor with create/edit/delete capabilities
- Admin controls for managing all articles
"""

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request, 
    abort, current_app, jsonify, make_response
)
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy import or_, desc
import re

from ..extensions import db
from ..models import BlogPost, User, Analysis, Company
from ..security import rate_limit, InputValidator, sanitize_input
from . import blog_bp
from ..utils.blog_ai_utils import (
    generate_seo_from_content,
    search_unsplash_images,
    get_featured_images_for_article,
    parse_document_file,
    generate_complete_article_from_file,
    enhance_existing_post
)


# ============================================================================
# PUBLIC ROUTES (SEO Optimized)
# ============================================================================

@blog_bp.route('/')
def index():
    """
    Blog homepage - list all published posts.
    SEO optimized with pagination and proper meta tags.
    Uses aggressive caching to minimize Neon DB compute unit usage.
    """
    page = request.args.get('page', 1, type=int)
    category = request.args.get('category', '')
    tag = request.args.get('tag', '')
    
    # Use cached data to avoid DB calls (Neon optimization)
    from ..utils.neon_cache import get_cached_blog_index
    
    cache_data = get_cached_blog_index(page=page, category=category, tag=tag)
    
    return render_template('blog/index.html',
                         posts=cache_data['posts'],
                         pagination=cache_data['pagination'],
                         categories=cache_data['categories'],
                         category_counts=cache_data['category_counts'],
                         featured_posts=cache_data['featured_posts'],
                         current_category=category,
                         current_tag=tag,
                         seo_title='KI Asset Management Blog | Investment Insights & Analysis',
                         seo_description='Expert investment analysis, market insights, and research from KI Asset Management. Student-driven financial research with institutional-grade quality.')


@blog_bp.route('/<slug>')
def post(slug):
    """
    Individual blog post page - SEO optimized.
    Uses caching for published posts to minimize DB calls.
    
    Args:
        slug: URL-friendly unique identifier for the post
    """
    import os
    
    # Find post by slug (always hit DB for permissions check)
    blog_post = BlogPost.query.filter_by(slug=slug).first_or_404()
    
    # Check visibility permissions
    if not blog_post.is_published:
        # Only author or admin can view unpublished posts
        if not current_user.is_authenticated:
            abort(404)
        if current_user.id != blog_post.author_id and not current_user.is_admin:
            abort(404)
    
    # Increment view count (but not for the author) - only for published posts
    if blog_post.is_published:
        if not current_user.is_authenticated or current_user.id != blog_post.author_id:
            # Skip view count increment in NEON_OPTIMIZE mode to reduce writes
            if os.environ.get('NEON_OPTIMIZE', 'true').lower() != 'true':
                blog_post.view_count += 1
                db.session.commit()
    
    # Get related posts (cached for public posts)
    if blog_post.is_published and os.environ.get('NEON_OPTIMIZE', 'true').lower() == 'true':
        # Use simpler related posts query to reduce DB load
        related_posts = BlogPost.query.filter(
            BlogPost.id != blog_post.id,
            BlogPost.status == 'published',
            BlogPost.is_public == True
        ).order_by(desc(BlogPost.published_at)).limit(3).all()
    else:
        related_posts = BlogPost.query.filter(
            BlogPost.id != blog_post.id,
            BlogPost.status == 'published',
            BlogPost.is_public == True
        ).filter(
            or_(
                BlogPost.category == blog_post.category if blog_post.category else False,
                BlogPost.author_id == blog_post.author_id
            )
        ).order_by(desc(BlogPost.published_at)).limit(3).all()
    
    # SEO meta values
    seo_title = blog_post.title
    seo_description = blog_post.meta_description or blog_post.get_excerpt(160)
    seo_keywords = blog_post.meta_keywords or 'investment, analysis, KI Asset Management, finance'
    og_image = blog_post.og_image or url_for('static', filename='images/og-default.jpg', _external=True)
    
    return render_template('blog/post.html',
                         post=blog_post,
                         related_posts=related_posts,
                         seo_title=seo_title,
                         seo_description=seo_description,
                         seo_keywords=seo_keywords,
                         og_image=og_image)


@blog_bp.route('/author/<int:user_id>')
def author_posts(user_id):
    """Show all posts by a specific author."""
    author = User.query.get_or_404(user_id)
    
    page = request.args.get('page', 1, type=int)
    per_page = 9
    
    # Only show published posts for public view
    query = BlogPost.query.filter(
        BlogPost.author_id == user_id,
        BlogPost.status == 'published',
        BlogPost.is_public == True
    ).order_by(desc(BlogPost.published_at))
    
    pagination = query.paginate(page=page, per_page=per_page)
    posts = pagination.items
    
    author_name = author.full_name or author.email.split('@')[0]
    
    return render_template('blog/author.html',
                         posts=posts,
                         pagination=pagination,
                         author=author,
                         author_name=author_name,
                         seo_title=f'Articles by {author_name} | KI Asset Management Blog',
                         seo_description=f'Read investment articles and analysis by {author_name} from KI Asset Management.')


@blog_bp.route('/feed.rss')
def rss_feed():
    """Generate RSS feed for blog posts. Uses caching to minimize DB calls."""
    from ..utils.neon_cache import get_cached_rss_posts
    
    posts = get_cached_rss_posts()
    
    response = make_response(render_template('blog/rss.xml', posts=posts))
    response.headers['Content-Type'] = 'application/rss+xml; charset=utf-8'
    return response


@blog_bp.route('/sitemap.xml')
def sitemap():
    """Generate XML sitemap for SEO. Uses caching to minimize DB calls."""
    from ..utils.neon_cache import get_cached_sitemap_posts
    
    posts = get_cached_sitemap_posts()
    
    response = make_response(render_template('blog/sitemap.xml', posts=posts))
    response.headers['Content-Type'] = 'application/xml; charset=utf-8'
    return response


# ============================================================================
# MEMBER ROUTES (Blog Editor)
# ============================================================================

@blog_bp.route('/my-posts')
@login_required
def my_posts():
    """Show current user's blog posts (drafts and published)."""
    page = request.args.get('page', 1, type=int)
    per_page = 12
    status_filter = request.args.get('status', '')
    
    query = BlogPost.query.filter(BlogPost.author_id == current_user.id)
    
    if status_filter:
        query = query.filter(BlogPost.status == status_filter)
    
    query = query.order_by(desc(BlogPost.updated_at))
    pagination = query.paginate(page=page, per_page=per_page)
    
    return render_template('blog/my_posts.html',
                         posts=pagination.items,
                         pagination=pagination,
                         status_filter=status_filter)


@blog_bp.route('/new', methods=['GET', 'POST'])
@login_required
@rate_limit(limit=10, window=3600)  # 10 new posts per hour
def new_post():
    """Create a new blog post."""
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        excerpt = request.form.get('excerpt', '').strip()
        meta_description = request.form.get('meta_description', '').strip()
        meta_keywords = request.form.get('meta_keywords', '').strip()
        category = request.form.get('category', '').strip()
        tags = request.form.get('tags', '').strip()
        content_type = request.form.get('content_type', 'html')
        is_public = request.form.get('is_public') == 'on'
        
        # Validation
        if not title:
            flash('Title is required.', 'danger')
            return redirect(url_for('blog.new_post'))
        
        if not content:
            flash('Content is required.', 'danger')
            return redirect(url_for('blog.new_post'))
        
        # Validate title length
        is_valid, sanitized_title, error = InputValidator.validate_length('title', title, max_length=255)
        if not is_valid:
            flash(error, 'danger')
            return redirect(url_for('blog.new_post'))
        
        # Create post
        blog_post = BlogPost(
            title=sanitized_title,
            content=content,
            excerpt=excerpt if excerpt else None,
            meta_description=meta_description[:300] if meta_description else None,
            meta_keywords=meta_keywords[:255] if meta_keywords else None,
            category=category if category else None,
            tags=tags if tags else None,
            content_type=content_type,
            is_public=is_public,
            author_id=current_user.id,
            status='draft'
        )
        
        # Generate unique slug
        blog_post.slug = blog_post.generate_slug()
        
        db.session.add(blog_post)
        db.session.commit()
        
        flash('Blog post created successfully! You can publish it when ready.', 'success')
        return redirect(url_for('blog.edit_post', post_id=blog_post.id))
    
    return render_template('blog/editor.html',
                         post=None,
                         categories=get_blog_categories())


@blog_bp.route('/edit/<int:post_id>', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    """
    Edit an existing blog post.
    Users can edit their own posts; admins can edit any post.
    """
    blog_post = BlogPost.query.get_or_404(post_id)
    
    # Check permissions
    if current_user.id != blog_post.author_id and not current_user.is_admin:
        flash('You can only edit your own posts.', 'danger')
        return redirect(url_for('blog.my_posts'))
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        excerpt = request.form.get('excerpt', '').strip()
        meta_description = request.form.get('meta_description', '').strip()
        meta_keywords = request.form.get('meta_keywords', '').strip()
        category = request.form.get('category', '').strip()
        tags = request.form.get('tags', '').strip()
        content_type = request.form.get('content_type', 'html')
        og_image = request.form.get('og_image', '').strip()
        is_public = request.form.get('is_public') == 'on'
        is_featured = request.form.get('is_featured') == 'on'
        
        # Validation
        if not title or not content:
            flash('Title and content are required.', 'danger')
            return redirect(url_for('blog.edit_post', post_id=post_id))
        
        # Validate title length
        is_valid, sanitized_title, error = InputValidator.validate_length('title', title, max_length=255)
        if not is_valid:
            flash(error, 'danger')
            return redirect(url_for('blog.edit_post', post_id=post_id))
        
        # Update fields
        blog_post.title = sanitized_title
        blog_post.content = content
        blog_post.excerpt = excerpt if excerpt else None
        blog_post.meta_description = meta_description[:300] if meta_description else None
        blog_post.meta_keywords = meta_keywords[:255] if meta_keywords else None
        blog_post.category = category if category else None
        blog_post.tags = tags if tags else None
        blog_post.content_type = content_type
        blog_post.og_image = og_image if og_image else None
        blog_post.is_public = is_public
        blog_post.updated_at = datetime.utcnow()
        
        # Handle publish date (admin only or if post is already published)
        if current_user.is_admin or blog_post.status == 'published':
            publish_date_str = request.form.get('publish_date', '').strip()
            if publish_date_str:
                try:
                    new_publish_date = datetime.strptime(publish_date_str, '%Y-%m-%dT%H:%M')
                    blog_post.published_at = new_publish_date
                except ValueError:
                    flash('Invalid publish date format.', 'warning')
        
        # Only admin can set featured
        if current_user.is_admin:
            blog_post.is_featured = is_featured
        
        db.session.commit()
        
        flash('Blog post updated successfully!', 'success')
        return redirect(url_for('blog.edit_post', post_id=post_id))
    
    return render_template('blog/editor.html',
                         post=blog_post,
                         categories=get_blog_categories())


@blog_bp.route('/delete/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    """
    Delete a blog post.
    Users can delete their own posts; admins can delete any post.
    Invalidates blog caches after deletion.
    """
    from ..utils.neon_cache import invalidate_blog_cache, invalidate_main_cache
    
    blog_post = BlogPost.query.get_or_404(post_id)
    
    # Check permissions
    if current_user.id != blog_post.author_id and not current_user.is_admin:
        flash('You can only delete your own posts.', 'danger')
        return redirect(url_for('blog.my_posts'))
    
    db.session.delete(blog_post)
    db.session.commit()
    
    # Invalidate caches after deletion
    try:
        invalidate_blog_cache()
        invalidate_main_cache()
    except Exception as e:
        current_app.logger.warning(f"Failed to invalidate caches: {e}")
    
    flash('Blog post deleted successfully.', 'success')
    
    # Redirect based on who deleted
    if current_user.is_admin and current_user.id != blog_post.author_id:
        return redirect(url_for('blog.admin_posts'))
    return redirect(url_for('blog.my_posts'))


@blog_bp.route('/publish/<int:post_id>', methods=['POST'])
@login_required
def publish_post(post_id):
    """
    Publish a draft post.
    Sets the post status to published and sets published_at date.
    Invalidates blog caches after publishing.
    """
    from ..utils.neon_cache import invalidate_blog_cache, invalidate_main_cache
    
    blog_post = BlogPost.query.get_or_404(post_id)
    
    # Check permissions
    if current_user.id != blog_post.author_id and not current_user.is_admin:
        flash('You can only publish your own posts.', 'danger')
        return redirect(url_for('blog.my_posts'))
    
    blog_post.status = 'published'
    blog_post.published_at = datetime.utcnow()
    blog_post.is_public = True  # Auto-set public when publishing
    db.session.commit()
    
    # Invalidate caches after publishing
    try:
        invalidate_blog_cache()
        invalidate_main_cache()
    except Exception as e:
        current_app.logger.warning(f"Failed to invalidate caches: {e}")
    
    flash('Blog post published successfully!', 'success')
    return redirect(url_for('blog.post', slug=blog_post.slug))


@blog_bp.route('/unpublish/<int:post_id>', methods=['POST'])
@login_required
def unpublish_post(post_id):
    """Unpublish a post - revert to draft status. Invalidates blog caches."""
    from ..utils.neon_cache import invalidate_blog_cache, invalidate_main_cache
    
    blog_post = BlogPost.query.get_or_404(post_id)
    
    # Check permissions
    if current_user.id != blog_post.author_id and not current_user.is_admin:
        flash('You can only unpublish your own posts.', 'danger')
        return redirect(url_for('blog.my_posts'))
    
    blog_post.status = 'draft'
    blog_post.is_public = False
    db.session.commit()
    
    # Invalidate caches after unpublishing
    try:
        invalidate_blog_cache()
        invalidate_main_cache()
    except Exception as e:
        current_app.logger.warning(f"Failed to invalidate caches: {e}")
    
    flash('Blog post unpublished and moved to drafts.', 'success')
    return redirect(url_for('blog.my_posts'))


@blog_bp.route('/preview/<int:post_id>')
@login_required
def preview_post(post_id):
    """Preview a post before publishing."""
    blog_post = BlogPost.query.get_or_404(post_id)
    
    # Check permissions
    if current_user.id != blog_post.author_id and not current_user.is_admin:
        abort(403)
    
    return render_template('blog/post.html',
                         post=blog_post,
                         is_preview=True,
                         related_posts=[],
                         seo_title=f'Preview: {blog_post.title}',
                         seo_description=blog_post.get_excerpt(160))


# ============================================================================
# ADMIN ROUTES
# ============================================================================

@blog_bp.route('/admin/posts')
@login_required
def admin_posts():
    """Admin view of all blog posts."""
    if not current_user.is_admin:
        abort(403)
    
    page = request.args.get('page', 1, type=int)
    per_page = 20
    status_filter = request.args.get('status', '')
    
    query = BlogPost.query
    
    if status_filter:
        query = query.filter(BlogPost.status == status_filter)
    
    query = query.order_by(desc(BlogPost.updated_at))
    pagination = query.paginate(page=page, per_page=per_page)
    
    return render_template('blog/admin_posts.html',
                         posts=pagination.items,
                         pagination=pagination,
                         status_filter=status_filter)


@blog_bp.route('/admin/toggle-featured/<int:post_id>', methods=['POST'])
@login_required
def toggle_featured(post_id):
    """Toggle featured status for a post (admin only)."""
    if not current_user.is_admin:
        abort(403)
    
    blog_post = BlogPost.query.get_or_404(post_id)
    blog_post.is_featured = not blog_post.is_featured
    db.session.commit()
    
    status = 'featured' if blog_post.is_featured else 'unfeatured'
    flash(f'Post {status} successfully!', 'success')
    
    return redirect(request.referrer or url_for('blog.admin_posts'))


# ============================================================================
# AJAX/API ROUTES
# ============================================================================

@blog_bp.route('/api/upload-image', methods=['POST'])
@login_required
def upload_image():
    """Handle image upload for blog posts."""
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Validate file type
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    
    if ext not in allowed_extensions:
        return jsonify({'error': 'Invalid file type. Allowed: PNG, JPG, GIF, WebP'}), 400
    
    # Save file with unique name
    from werkzeug.utils import secure_filename
    import os
    from flask import current_app
    
    filename = secure_filename(f"blog_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{file.filename}")
    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'blog')
    os.makedirs(upload_folder, exist_ok=True)
    
    filepath = os.path.join(upload_folder, filename)
    file.save(filepath)
    
    # Return URL
    image_url = url_for('static', filename=f'uploads/blog/{filename}')
    return jsonify({'url': image_url})


@blog_bp.route('/api/render-markdown', methods=['POST'])
@login_required
def render_markdown():
    """Render markdown content to HTML for preview."""
    content = request.json.get('content', '')
    
    try:
        import markdown
        md = markdown.Markdown(extensions=['extra', 'codehilite', 'toc'])
        html = md.convert(content)
        return jsonify({'html': html})
    except ImportError:
        # Fallback: simple formatting
        html = content.replace('\n\n', '</p><p>').replace('\n', '<br>')
        return jsonify({'html': f'<p>{html}</p>'})


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_blog_categories():
    """Get list of existing categories for dropdown."""
    categories = db.session.query(BlogPost.category).filter(
        BlogPost.category != None,
        BlogPost.category != ''
    ).distinct().all()
    return sorted([c[0] for c in categories])


def get_latest_posts(limit=6, featured_only=False):
    """Helper to get latest posts for embedding in other pages."""
    query = BlogPost.query.filter(
        BlogPost.status == 'published',
        BlogPost.is_public == True
    )
    
    if featured_only:
        query = query.filter(BlogPost.is_featured == True)
    
    return query.order_by(desc(BlogPost.published_at)).limit(limit).all()


# ============================================================================
# AI-ASSISTED CONTENT ROUTES
# ============================================================================

@blog_bp.route('/api/generate-seo', methods=['POST'])
@login_required
@rate_limit(limit=20, window=3600)  # 20 SEO generations per hour
def generate_seo_api():
    """
    API endpoint to generate SEO metadata from title and content using DeepSeek AI.
    Also searches for relevant Unsplash images (returns 6 for user to choose).
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    title = data.get('title', '').strip()
    content = data.get('content', '').strip()
    category = data.get('category', '').strip()
    
    # Validate input lengths to prevent abuse
    if len(title) > 500 or len(content) > 50000:
        return jsonify({'error': 'Content too long'}), 400
    
    if not title or not content:
        return jsonify({'error': 'Title and content are required'}), 400
    
    try:
        # Generate SEO data using DeepSeek
        seo_data = generate_seo_from_content(title, content)
        
        # Search for featured images (up to 30 images for user to choose)
        images = get_featured_images_for_article(title, content, category, count=30)
        
        result = {
            'success': True,
            'meta_description': seo_data.get('meta_description', ''),
            'meta_keywords': seo_data.get('meta_keywords', ''),
            'excerpt': seo_data.get('excerpt', ''),
            'suggested_tags': seo_data.get('suggested_tags', '')
        }
        
        if images:
            result['images'] = images
            result['image_count'] = len(images)
            # Auto-select first image as default
            result['og_image'] = images[0]['url']
        
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Error generating SEO: {e}")
        return jsonify({'error': 'Failed to generate SEO metadata'}), 500


@blog_bp.route('/api/search-unsplash', methods=['POST'])
@login_required
@rate_limit(limit=50, window=3600)  # 50 image searches per hour
def search_unsplash_api():
    """
    API endpoint to search for images on Unsplash.
    Returns up to 30 images for the user to choose from.
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    query = data.get('query', '').strip()
    orientation = data.get('orientation', 'landscape')
    count = data.get('count', 6)
    
    # Validate inputs
    if len(query) > 200:
        return jsonify({'error': 'Search query too long'}), 400
    
    # Limit count to prevent abuse (max 30 per Unsplash API)
    count = min(max(count, 1), 30)
    
    if not query:
        return jsonify({'error': 'Search query is required'}), 400
    
    try:
        images = search_unsplash_images(query, orientation, count=count)
        
        if images:
            return jsonify({
                'success': True,
                'images': images,
                'count': len(images),
                'query': query
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No images found for this query',
                'query': query
            }), 404
            
    except Exception as e:
        current_app.logger.error(f"Error searching Unsplash: {e}")
        return jsonify({'error': 'Failed to search Unsplash'}), 500


@blog_bp.route('/api/upload-document', methods=['POST'])
@login_required
@rate_limit(limit=5, window=3600)  # 5 document uploads per hour
def upload_document():
    """
    Upload and parse a PDF or DOCX file, then generate a complete blog article.
    Security: Max file size 10MB, allowed types: PDF, DOCX, DOC
    """
    if 'document' not in request.files:
        return jsonify({'error': 'No document provided'}), 400
    
    file = request.files['document']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Validate file type
    allowed_extensions = {'pdf', 'docx', 'doc'}
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    
    if ext not in allowed_extensions:
        return jsonify({
            'error': 'Invalid file type. Allowed: PDF, DOCX, DOC'
        }), 400
    
    # Validate file size (10MB max)
    max_file_size = 10 * 1024 * 1024  # 10MB
    file.seek(0, 2)  # Seek to end of file
    file_size = file.tell()
    file.seek(0)  # Reset to beginning
    
    if file_size > max_file_size:
        return jsonify({
            'error': 'File too large. Maximum size is 10MB.'
        }), 400
    
    if file_size == 0:
        return jsonify({'error': 'File is empty'}), 400
    
    target_style = request.form.get('target_style', 'seo_article')
    
    # Validate style
    valid_styles = {'seo_article', 'academic_paper', 'blog_post', 'investment_pitch'}
    if target_style not in valid_styles:
        target_style = 'seo_article'
    
    try:
        # Save file temporarily
        from werkzeug.utils import secure_filename
        import os
        import tempfile
        
        filename = secure_filename(f"upload_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{file.filename}")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{ext}') as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name
        
        try:
            # Process the document
            result = generate_complete_article_from_file(tmp_path, ext, target_style)
            return jsonify(result)
        finally:
            # Clean up temp file
            try:
                os.unlink(tmp_path)
            except:
                pass
                
    except Exception as e:
        current_app.logger.error(f"Error processing document: {e}")
        return jsonify({'error': f'Failed to process document: {str(e)}'}), 500


@blog_bp.route('/api/enhance-post', methods=['POST'])
@login_required
def enhance_post_api():
    """
    API endpoint to enhance an existing post with AI-generated SEO and image.
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    try:
        result = enhance_existing_post(data)
        return jsonify(result)
    except Exception as e:
        current_app.logger.error(f"Error enhancing post: {e}")
        return jsonify({'error': 'Failed to enhance post'}), 500


@blog_bp.route('/api/find-analysis-date', methods=['POST'])
@login_required
@rate_limit(limit=20, window=3600)  # 20 searches per hour
def find_analysis_date_api():
    """
    API endpoint to find analysis dates by company name or ticker.
    Returns matching analyses with their dates for the editor to choose from.
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    search_term = data.get('search_term', '').strip()
    
    if not search_term or len(search_term) < 2:
        return jsonify({'error': 'Search term must be at least 2 characters'}), 400
    
    if len(search_term) > 100:
        return jsonify({'error': 'Search term too long'}), 400
    
    try:
        search_pattern = f"%{search_term}%"
        
        # Search for companies matching the term (by name or ticker)
        matching_companies = Company.query.filter(
            db.or_(
                Company.name.ilike(search_pattern),
                Company.ticker_symbol.ilike(search_pattern)
            )
        ).all()
        
        if not matching_companies:
            return jsonify({
                'success': True,
                'analyses': [],
                'message': 'No companies found matching your search'
            })
        
        # Get analyses for these companies
        company_ids = [c.id for c in matching_companies]
        analyses = Analysis.query.filter(
            Analysis.company_id.in_(company_ids)
        ).order_by(Analysis.analysis_date.desc()).all()
        
        results = []
        for analysis in analyses:
            company = Company.query.get(analysis.company_id)
            if company:
                results.append({
                    'analysis_id': analysis.id,
                    'company_name': company.name,
                    'ticker_symbol': company.ticker_symbol,
                    'analysis_date': analysis.analysis_date.isoformat() if analysis.analysis_date else None,
                    'formatted_date': analysis.analysis_date.strftime('%Y-%m-%d') if analysis.analysis_date else 'Unknown',
                    'status': analysis.status
                })
        
        return jsonify({
            'success': True,
            'analyses': results,
            'count': len(results)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error finding analysis date: {e}")
        return jsonify({'error': 'Failed to search analyses'}), 500
