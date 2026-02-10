"""
Blog AI utilities for generating SEO content and finding images.

This module provides:
- DeepSeek API integration for SEO optimization
- Unsplash API integration for finding relevant images
- Document parsing and article generation from PDF/DOCX files
"""

import logging
import requests
import json
import re
from typing import Optional, Dict, Any, List
from flask import current_app

logger = logging.getLogger(__name__)


# =============================================================================
# DeepSeek API Functions
# =============================================================================

def generate_seo_from_content(title: str, content: str) -> Dict[str, str]:
    """
    Generate SEO metadata from blog post content using DeepSeek API.
    
    Args:
        title: The blog post title
        content: The blog post content (HTML or plain text)
    
    Returns:
        Dictionary with meta_description, meta_keywords, excerpt, and suggested_tags
    """
    api_key = current_app.config.get('DEEPSEEK_API_KEY')
    if not api_key:
        logger.warning("DeepSeek API key not configured")
        return _fallback_seo(title, content)
    
    # Clean content - remove HTML tags for better processing
    clean_content = re.sub(r'<[^>]+>', ' ', content)
    clean_content = re.sub(r'\s+', ' ', clean_content).strip()[:2000]  # Limit length
    
    prompt = f"""Given the following blog post title and content, generate SEO-optimized metadata.

Title: {title}

Content: {clean_content}

Please provide:
1. Meta Description (150-160 characters, compelling for search results)
2. Meta Keywords (5-10 relevant keywords, comma-separated)
3. Excerpt (brief 2-3 sentence summary for previews)
4. Suggested Tags (5-8 relevant tags, comma-separated)

Format your response EXACTLY as JSON:
{{
    "meta_description": "...",
    "meta_keywords": "...",
    "excerpt": "...",
    "suggested_tags": "..."
}}
"""
    
    try:
        response = call_deepseek(prompt, max_tokens=800, temperature=0.3)
        if response:
            # Extract JSON from response
            json_match = re.search(r'\{[^}]*\}', response, re.DOTALL)
            if json_match:
                seo_data = json.loads(json_match.group())
                return {
                    'meta_description': seo_data.get('meta_description', '')[:300],
                    'meta_keywords': seo_data.get('meta_keywords', '')[:255],
                    'excerpt': seo_data.get('excerpt', ''),
                    'suggested_tags': seo_data.get('suggested_tags', '')
                }
    except Exception as e:
        logger.error(f"Error generating SEO with DeepSeek: {e}")
    
    return _fallback_seo(title, content)


def _fallback_seo(title: str, content: str) -> Dict[str, str]:
    """Generate basic SEO data when AI is unavailable."""
    clean_content = re.sub(r'<[^>]+>', ' ', content)
    clean_content = re.sub(r'\s+', ' ', clean_content).strip()
    
    # Generate excerpt from first 200 chars
    excerpt = clean_content[:200] + '...' if len(clean_content) > 200 else clean_content
    
    # Basic meta description
    meta_description = excerpt[:160] if len(excerpt) > 160 else excerpt
    
    # Extract potential keywords from title
    words = re.findall(r'\b[A-Za-z]{4,}\b', title)
    keywords = ', '.join(list(set(words))[:8]) if words else 'investment, analysis, finance'
    
    return {
        'meta_description': meta_description,
        'meta_keywords': keywords,
        'excerpt': excerpt,
        'suggested_tags': keywords
    }


def generate_article_from_document(doc_text: str, doc_type: str = 'pdf', 
                                    target_style: str = 'seo_article') -> Dict[str, Any]:
    """
    Generate a complete blog article from parsed document content.
    
    Args:
        doc_text: The extracted text content from the document
        doc_type: Type of document ('pdf', 'docx', etc.)
        target_style: Target style ('seo_article', 'academic_paper', 'blog_post')
    
    Returns:
        Dictionary with title, content, seo metadata, and image keywords
    """
    api_key = current_app.config.get('DEEPSEEK_API_KEY')
    if not api_key:
        logger.warning("DeepSeek API key not configured")
        return _fallback_document_conversion(doc_text)
    
    # Limit document length to avoid token limits
    doc_text = doc_text[:4000] + ('...' if len(doc_text) > 4000 else '')
    
    style_instructions = {
        'seo_article': """Transform this into an SEO-optimized blog article:
- Engaging, accessible language
- Clear headings and subheadings (H2, H3)
- Bullet points for key takeaways
- Include a compelling introduction and conclusion
- Add "Key Takeaways" section at the end""",
        'academic_paper': """Transform this into an academic-style research paper:
- Formal, professional tone
- Structured sections: Abstract, Introduction, Analysis, Conclusion
- Objective, evidence-based presentation
- Include methodology section if applicable
- Professional citations format""",
        'blog_post': """Transform this into a compelling blog post:
- Conversational but professional tone
- Storytelling elements
- Personal insights and analysis
- Engaging subheadings
- Call-to-action at the end""",
        'investment_pitch': """Transform this stock analysis into a PERSUASIVE INVESTMENT PITCH:
- Lead with the investment thesis - WHY this is a compelling opportunity
- Use persuasive, confident language that builds conviction
- Structure as: Executive Summary (the pitch), Business Overview, Investment Case (bull case), Risk Factors (brief), Valuation, Conclusion with clear BUY/HOLD/SELL recommendation
- Include specific numbers: target price, upside potential, key metrics
- Address the "so what" - why should investors care NOW
- Use bold for key investment highlights
- Include a "Bottom Line" section with actionable recommendation
- Tone: Professional but compelling, like a top-tier equity research report"""
    }
    
    # Validate target_style, fallback to seo_article if invalid
    valid_styles = {'seo_article', 'academic_paper', 'blog_post', 'investment_pitch'}
    if target_style not in valid_styles:
        target_style = 'seo_article'
    
    style_prompt = style_instructions.get(target_style, style_instructions['seo_article'])
    
    is_pitch = target_style == 'investment_pitch'
    
    prompt = f"""You are a professional financial content writer and equity analyst. Convert the following document into a high-quality, comprehensive article.

{style_prompt}

Original Document:
{doc_text}

Please provide your response in this EXACT JSON format:
{{
    "title": "{'Compelling investment pitch title with ticker (60-70 characters)' if is_pitch else 'Compelling, SEO-friendly title (60-70 characters)'}",
    "content": "Full HTML-formatted article content with proper headings (H2, H3), paragraphs, bullet points, and formatting. {'Include investment highlights, financial metrics, and clear BUY/HOLD/SELL recommendation.' if is_pitch else 'Make it comprehensive and engaging.'}",
    "excerpt": "Brief 2-3 sentence summary that captures the main thesis/point",
    "meta_description": "SEO meta description (150-160 characters)",
    "meta_keywords": "Comma-separated keywords for SEO",
    "category": "Suggested category (Market Analysis, Investment Strategy, Company Research, Education, or News)",
    "tags": "Comma-separated relevant tags",
    "image_keywords": "3-5 keywords for finding a relevant featured image"
}}

Critical Requirements:
- Return ONLY the JSON, no other text
- Ensure all HTML tags are properly closed
- {'For investment pitch: Be thorough and analytical. Include specific metrics, valuation multiples, and comparison to peers where available. Make it 1500+ words.' if is_pitch else 'Make the content comprehensive but readable (800-1500 words)'}
- Include specific data, numbers, and insights from the original document
- {'Structure with clear sections: Investment Thesis, Business Overview, Financial Analysis, Valuation, Risks, and Recommendation' if is_pitch else 'Use clear headings and subheadings'}
- Use proper HTML: <h2> for main sections, <h3> for subsections, <p> for paragraphs, <ul>/<li> for bullet points"""
    
    try:
        # Use more tokens for investment pitch to ensure thorough analysis
        max_tokens = 4000 if is_pitch else 3000
        response = call_deepseek(prompt, max_tokens=max_tokens, temperature=0.4)
        if response:
            # Extract JSON from response
            json_match = re.search(r'\{[^}]*\}', response, re.DOTALL)
            if json_match:
                article_data = json.loads(json_match.group())
                
                # Validate and clean the data
                return {
                    'title': article_data.get('title', 'Untitled Article')[:255],
                    'content': article_data.get('content', doc_text),
                    'excerpt': article_data.get('excerpt', '')[:500],
                    'meta_description': article_data.get('meta_description', '')[:300],
                    'meta_keywords': article_data.get('meta_keywords', '')[:255],
                    'category': article_data.get('category', 'Market Analysis'),
                    'tags': article_data.get('tags', ''),
                    'image_keywords': article_data.get('image_keywords', 'finance business')
                }
    except Exception as e:
        logger.error(f"Error generating article with DeepSeek: {e}")
    
    return _fallback_document_conversion(doc_text)


def _fallback_document_conversion(doc_text: str) -> Dict[str, Any]:
    """Fallback conversion when AI is unavailable."""
    # Basic HTML formatting
    paragraphs = [p.strip() for p in doc_text.split('\n\n') if p.strip()]
    html_content = '\n\n'.join([f'<p>{p}</p>' for p in paragraphs[:20]])
    
    # Extract first sentence as title
    first_sentence = doc_text.split('.')[0] if '.' in doc_text else doc_text[:70]
    title = first_sentence[:70] + '...' if len(first_sentence) > 70 else first_sentence
    
    excerpt = doc_text[:200] + '...' if len(doc_text) > 200 else doc_text
    
    return {
        'title': title or 'Document Analysis',
        'content': html_content or doc_text[:2000],
        'excerpt': excerpt,
        'meta_description': excerpt[:160],
        'meta_keywords': 'investment, analysis, research, finance',
        'category': 'Market Analysis',
        'tags': 'analysis, research',
        'image_keywords': 'finance business stock market'
    }


def call_deepseek(prompt: str, max_tokens: int = 500, temperature: float = 0.3) -> Optional[str]:
    """Make a request to DeepSeek chat completions API."""
    api_key = current_app.config.get('DEEPSEEK_API_KEY')
    if not api_key:
        return None
    
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": temperature
    }
    
    try:
        logger.debug(f"Calling DeepSeek API with prompt length: {len(prompt)}")
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        response_text = data['choices'][0]['message']['content'].strip()
        logger.debug(f"DeepSeek API response received, length: {len(response_text)}")
        return response_text
    except Exception as e:
        logger.error(f"DeepSeek API error: {e}")
        return None


# =============================================================================
# Unsplash API Functions
# =============================================================================

def search_unsplash_images(query: str, orientation: str = 'landscape', 
                           count: int = 6) -> List[Dict[str, Any]]:
    """
    Search for relevant images on Unsplash.
    
    Args:
        query: Search query (keywords)
        orientation: Image orientation ('landscape', 'portrait', 'squarish')
        count: Number of images to return (max 100)
    
    Returns:
        List of dictionaries with image URL, author info, and attribution
    """
    api_key = current_app.config.get('UNSPLASH_API_KEY')
    if not api_key:
        logger.warning("Unsplash API key not configured")
        return []
    
    url = "https://api.unsplash.com/search/photos"
    headers = {
        "Authorization": f"Client-ID {api_key}"
    }
    params = {
        "query": query,
        "orientation": orientation,
        "per_page": min(count, 30),  # Unsplash API max is 30 per request
        "order_by": "relevant"
    }
    
    try:
        logger.debug(f"Searching Unsplash for: {query}")
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        results = []
        if data.get('results'):
            for image in data['results'][:count]:
                results.append({
                    'id': image['id'],
                    'url': image['urls']['regular'],
                    'thumb_url': image['urls']['small'],
                    'download_url': image['urls']['full'],
                    'author_name': image['user']['name'],
                    'author_username': image['user']['username'],
                    'author_url': image['user']['links']['html'],
                    'photo_url': image['links']['html'],
                    'description': image.get('description') or image.get('alt_description', ''),
                    'width': image['width'],
                    'height': image['height']
                })
        
        if not results:
            logger.warning(f"No Unsplash results for query: {query}")
        
        return results
            
    except Exception as e:
        logger.error(f"Unsplash API error: {e}")
        return []


def search_unsplash_image(query: str, orientation: str = 'landscape') -> Optional[Dict[str, Any]]:
    """
    Search for a single relevant image on Unsplash (backwards compatibility).
    
    Args:
        query: Search query (keywords)
        orientation: Image orientation ('landscape', 'portrait', 'squarish')
    
    Returns:
        Dictionary with image URL, author info, and attribution
    """
    images = search_unsplash_images(query, orientation, count=1)
    return images[0] if images else None


def get_featured_images_for_article(title: str, content: str, 
                                     category: str = None, count: int = 6) -> List[Dict[str, Any]]:
    """
    Get featured images for a blog article based on its content.
    Implements multi-level fallback: full query -> single keywords -> generic finance terms.
    
    Args:
        title: Article title
        content: Article content
        category: Article category
        count: Number of images to return
    
    Returns:
        List of dictionaries with image info
    """
    # Build search query from available info
    search_terms = []
    
    if category:
        search_terms.append(category.lower())
    
    # Extract key terms from title (words 4+ chars)
    title_words = re.findall(r'\b[A-Za-z]{4,}\b', title)
    if title_words:
        search_terms.extend(title_words[:3])
    
    # Default finance terms if nothing specific found
    if not search_terms:
        search_terms = ['finance', 'business', 'investment']
    
    # Level 1: Try specific search with combined terms
    query = ' '.join(search_terms[:4])
    results = search_unsplash_images(query, count=count)
    
    # Level 2: If no results, try single keywords from title one by one
    if not results and title_words:
        # Try most relevant single words (prioritize longer words and common image terms)
        image_friendly_terms = ['business', 'technology', 'office', 'meeting', 'charts', 
                               'data', 'city', 'building', 'work', 'team', 'growth']
        for word in title_words:
            word_lower = word.lower()
            # Skip ticker symbols (all caps, short)
            if word.isupper() and len(word) <= 5:
                continue
            single_results = search_unsplash_images(word_lower, count=count)
            if single_results:
                results = single_results
                logger.info(f"Found {len(results)} images using single keyword: {word_lower}")
                break
    
    # Level 3: Try category alone if still no results
    if not results and category:
        results = search_unsplash_images(category.lower(), count=count)
    
    # Level 4: Fallback to generic finance search
    if not results:
        results = search_unsplash_images('finance business technology', count=count)
    
    return results


def get_featured_image_for_article(title: str, content: str, 
                                    category: str = None) -> Optional[Dict[str, Any]]:
    """
    Get a single featured image for a blog article (backwards compatibility).
    
    Args:
        title: Article title
        content: Article content
        category: Article category
    
    Returns:
        Dictionary with image info or None
    """
    images = get_featured_images_for_article(title, content, category, count=1)
    return images[0] if images else None


# =============================================================================
# Document Parsing Functions
# =============================================================================

def parse_document_file(file_path: str, file_extension: str) -> str:
    """
    Parse content from a PDF or DOCX file.
    
    Args:
        file_path: Path to the file
        file_extension: File extension ('pdf', 'docx')
    
    Returns:
        Extracted text content
    """
    if file_extension.lower() == 'pdf':
        return parse_pdf(file_path)
    elif file_extension.lower() in ['docx', 'doc']:
        return parse_docx(file_path)
    else:
        # Try to read as plain text
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            return ""


def parse_pdf(file_path: str) -> str:
    """Extract text from a PDF file."""
    try:
        # Try PyPDF2 first (usually available)
        import PyPDF2
        text = ""
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() + "\n\n"
        return text.strip()
    except ImportError:
        logger.warning("PyPDF2 not installed, trying pdfplumber")
    except Exception as e:
        logger.error(f"PyPDF2 error: {e}")
    
    try:
        # Try pdfplumber as fallback
        import pdfplumber
        text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() or ""
                text += "\n\n"
        return text.strip()
    except ImportError:
        logger.warning("pdfplumber not installed")
    except Exception as e:
        logger.error(f"pdfplumber error: {e}")
    
    return "Could not parse PDF. Please install PyPDF2: pip install PyPDF2"


def parse_docx(file_path: str) -> str:
    """Extract text from a DOCX file."""
    try:
        from docx import Document
        doc = Document(file_path)
        text = []
        for para in doc.paragraphs:
            text.append(para.text)
        return '\n\n'.join(text)
    except ImportError:
        logger.warning("python-docx not installed")
        return "Could not parse DOCX. Please install python-docx: pip install python-docx"
    except Exception as e:
        logger.error(f"DOCX parsing error: {e}")
        return f"Error parsing DOCX: {str(e)}"


# =============================================================================
# Combined Workflow Functions
# =============================================================================

def generate_complete_article_from_file(file_path: str, file_extension: str,
                                        target_style: str = 'seo_article') -> Dict[str, Any]:
    """
    Complete workflow: parse document, generate article, get SEO, and find images.
    
    Args:
        file_path: Path to the uploaded document
        file_extension: File extension
        target_style: Target article style
    
    Returns:
        Complete article data ready for blog post creation
    """
    # Step 1: Parse the document
    logger.info(f"Parsing document: {file_path}")
    doc_text = parse_document_file(file_path, file_extension)
    
    if not doc_text or len(doc_text) < 100:
        return {
            'success': False,
            'error': 'Could not extract sufficient text from the document'
        }
    
    # Step 2: Generate article from document
    logger.info("Generating article with DeepSeek")
    article_data = generate_article_from_document(doc_text, file_extension, target_style)
    
    # Step 3: Get featured images (up to 30 images for user to choose)
    logger.info("Searching for featured images")
    images = get_featured_images_for_article(
        article_data['title'],
        article_data['content'],
        article_data.get('category'),
        count=30
    )
    
    if images:
        article_data['images'] = images
        article_data['image_count'] = len(images)
        # Auto-select first image as default
        article_data['og_image'] = images[0]['url']
        article_data['featured_image'] = images[0]
    
    article_data['success'] = True
    return article_data


def enhance_existing_post(post_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enhance an existing blog post with AI-generated SEO and image.
    
    Args:
        post_data: Dictionary with title, content, category
    
    Returns:
        Enhanced post data with SEO fields and image
    """
    title = post_data.get('title', '')
    content = post_data.get('content', '')
    category = post_data.get('category', '')
    
    # Generate SEO
    seo_data = generate_seo_from_content(title, content)
    
    # Get featured image
    image_data = get_featured_image_for_article(title, content, category)
    
    result = {
        **seo_data,
        'success': True
    }
    
    if image_data:
        result['og_image'] = image_data['url']
        result['featured_image'] = image_data
    
    return result
