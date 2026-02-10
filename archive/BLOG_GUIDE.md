# Blog System Guide

Complete guide for using the KI Asset Management blog system with AI-powered features.

---

## Table of Contents

1. [Overview](#overview)
2. [Getting Started](#getting-started)
3. [Writing Articles](#writing-articles)
4. [AI-Powered Features](#ai-powered-features)
5. [Document Import](#document-import)
6. [SEO Best Practices](#seo-best-practices)
7. [Security & Limits](#security--limits)

---

## Overview

The blog system provides a complete content management solution with:

- **SEO Optimization**: Automatic meta tags, keywords, and social sharing
- **AI Content Generation**: Convert documents into full articles
- **Image Integration**: Unsplash search with 6-image selection
- **Multiple Formats**: Support for HTML and Markdown
- **Public/Private Control**: Choose visibility for each post

---

## Getting Started

### Prerequisites

To use all AI features, ensure these environment variables are set:

```bash
# Required for AI content generation
DEEPSEEK_API_KEY=your_deepseek_key

# Required for featured images
UNSPLASH_API_KEY=your_unsplash_key
```

### Creating Your First Post

1. Navigate to **Blog → New Post** (or `/blog/new`)
2. Enter your article title and content
3. Click **"Auto-Generate with AI"** for SEO optimization
4. Select a featured image from the gallery
5. Click **"Save Draft"** or **"Publish"**

---

## Writing Articles

### Editor Features

The blog editor includes:

- **HTML Toolbar**: Insert headings, paragraphs, bold, italic, lists, links, images
- **Image Upload**: Upload your own images directly
- **Markdown Support**: Write in Markdown (converted to HTML)
- **Auto-Save**: Drafts are preserved while editing

### Content Fields

| Field | Required | Description |
|-------|----------|-------------|
| Title | ✅ | Article headline (max 255 chars) |
| Content | ✅ | Main article body (HTML or Markdown) |
| Excerpt | ❌ | Short summary for previews (auto-generated) |
| Category | ❌ | Organize posts (e.g., "Market Analysis") |
| Tags | ❌ | Comma-separated keywords |
| Meta Description | ❌ | SEO snippet (150-160 chars, auto-generated) |
| Meta Keywords | ❌ | SEO keywords (auto-generated) |
| Featured Image | ❌ | Social sharing image (auto-suggested) |

### Post Status

- **Draft**: Private, only visible to author
- **Published**: Public, appears in blog listing
- **Featured**: Highlighted on main page (admin only)

---

## AI-Powered Features

### SEO Auto-Generation

Click **"Auto-Generate with AI"** to automatically create:

1. **Meta Description**: Compelling 150-160 character summary
2. **Meta Keywords**: Relevant SEO keywords
3. **Excerpt**: Brief preview text
4. **Suggested Tags**: Categorized labels
5. **Featured Images**: 6 curated Unsplash images to choose from

### Image Selection Gallery

After AI generation, you'll see 6 image thumbnails:

- First image is auto-selected (highlighted with blue border)
- Click any image to select it instead
- Images include proper Unsplash attribution
- Selected image URL is inserted into "Featured Image URL" field

---

## Document Import

Transform PDFs and DOCX files into complete blog articles.

### Supported Styles

| Style | Best For | Output |
|-------|----------|--------|
| **SEO Article** | General content | Web-optimized with headings, bullet points |
| **Investment Pitch** | Stock analyses | BUY/HOLD/SELL recommendation, target price |
| **Academic Paper** | Research reports | Formal structure with Abstract, Analysis |
| **Blog Post** | Casual content | Conversational, storytelling format |

### Using Document Import

1. On the **New Post** page, scroll to "AI-Powered Document Import"
2. Select your file (PDF, DOCX, or DOC)
3. Choose the target style
4. Click **"Generate Article"**
5. Review and edit the generated content
6. Select a featured image
7. Save or publish

### Investment Pitch Style

Perfect for stock analyses, this style includes:

- **Executive Summary**: The core investment thesis upfront
- **Business Overview**: Company description and model
- **Investment Case**: Bull case with supporting data
- **Risk Factors**: Key risks (brief but comprehensive)
- **Valuation**: Target price and upside potential
- **Bottom Line**: Clear BUY/HOLD/SELL recommendation

**Example Output Structure:**
```html
<h2>Executive Summary</h2>
<p>Why this is a compelling opportunity now...</p>

<h2>Investment Thesis</h2>
<ul>
  <li>Key growth driver 1</li>
  <li>Competitive advantage</li>
  <li>Valuation opportunity</li>
</ul>

<h2>Valuation & Target Price</h2>
<p>Target: $XX.XX (XX% upside)</p>

<h2>Bottom Line: BUY</h2>
<p>Actionable recommendation...</p>
```

---

## SEO Best Practices

### Writing SEO-Friendly Titles

- Keep under 60 characters
- Include main keyword near the beginning
- Be descriptive but compelling
- Examples:
  - ✅ "Bilibili Stock Analysis: Why BILI is a Hidden Gem"
  - ❌ "Stock Analysis" (too vague)

### Meta Descriptions

- 150-160 characters ideal
- Include call-to-action
- Mention key benefit/value
- Examples:
  - ✅ "Discover why Bilibili's undervalued stock presents a compelling investment opportunity with 40% upside potential. Read our comprehensive analysis."

### Using Tags Effectively

- Use 5-8 relevant tags
- Mix broad and specific: "stocks", "china", "tech", "bilibili"
- Include ticker symbols: "BILI", "TSLA"
- Avoid duplicates (already covered by category)

### Featured Images

- Minimum 1200x630px for optimal social sharing
- Use landscape orientation
- Choose relevant, professional images
- Always include proper attribution (handled automatically)

---

## Security & Limits

### Rate Limiting

To prevent abuse and manage API costs:

| Feature | Limit | Window |
|---------|-------|--------|
| SEO Generation | 20 requests | 1 hour |
| Image Search | 30 searches | 1 hour |
| Document Upload | 5 uploads | 1 hour |
| New Posts | 10 posts | 1 hour |

### File Upload Security

- **Max File Size**: 10MB
- **Allowed Types**: PDF, DOCX, DOC only
- **Validation**: File extension and MIME type checked
- **Storage**: Files processed in temporary directory, immediately deleted after processing
- **Content**: Document text extracted but never stored permanently

### API Key Security

- API keys are never exposed to frontend
- All AI calls happen server-side
- No user content is logged or stored by AI services (beyond normal API usage)
- Rate limiting prevents API abuse

### Content Guidelines

- All posts are attributed to the author
- Only authors and admins can edit posts
- Public posts are visible to everyone
- Drafts are private to the author
- Featured posts require admin approval

---

## Troubleshooting

### "No images found" Error

- Try more generic search terms
- Check that `UNSPLASH_API_KEY` is set correctly
- Unsplash may have limited results for very specific queries

### Document Import Fails

- Ensure file is under 10MB
- Check that file is not password-protected
- Try converting to PDF if DOCX fails
- Ensure `DEEPSEEK_API_KEY` is configured

### SEO Generation Slow

- Large documents (>4000 words) take longer
- AI generation typically takes 10-30 seconds
- If timeout occurs, try with shorter content

### Changes Not Saving

- Check that title and content are not empty
- Ensure CSRF token is valid (refresh page if needed)
- Check browser console for JavaScript errors

---

## FAQ

**Q: Can I edit AI-generated content?**  
A: Yes! AI-generated content is a starting point. Always review and edit before publishing.

**Q: Are uploaded documents stored?**  
A: No. Documents are processed temporarily and deleted immediately after text extraction.

**Q: Can I use the blog without AI features?**  
A: Yes. All AI features are optional. You can write and publish posts manually.

**Q: Who can see my drafts?**  
A: Only you. Drafts are private until published.

**Q: How do I feature a post on the main page?**  
A: Admin users can mark posts as "Featured" in the post editor.

---

## Support

For technical issues or feature requests:

1. Check this guide first
2. Review the troubleshooting section
3. Contact the admin team
