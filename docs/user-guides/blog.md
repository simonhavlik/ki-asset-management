# Blog System Guide

Complete guide to using the KI Asset Management blog system.

---

## 📝 Overview

The blog system includes:

- **SEO Optimization** - Automatic meta tags and keywords
- **AI-Powered Features** - Content generation and optimization
- **Image Integration** - Unsplash search and selection
- **Document Import** - Convert PDFs/DOCX to blog posts
- **Multiple Formats** - HTML and Markdown support

---

## 🚀 Creating a Post

### Basic Post Creation

1. Navigate to **Blog → New Post** or `/blog/new`
2. Fill in the fields:
   - **Title** (required) - Article headline
   - **Content** (required) - Main article body
   - **Category** - Topic organization
   - **Tags** - Comma-separated keywords
3. Click **Save Draft** or **Publish**

### Content Fields

| Field | Required | Description |
|-------|----------|-------------|
| Title | ✅ | Article headline (max 255 chars) |
| Content | ✅ | Main body (HTML or Markdown) |
| Excerpt | ❌ | Short summary for previews |
| Category | ❌ | Organize posts (e.g., "Market Analysis") |
| Tags | ❌ | Comma-separated keywords |
| Meta Description | ❌ | SEO snippet (150-160 chars) |
| Meta Keywords | ❌ | SEO keywords |
| Featured Image | ❌ | Social sharing image |

---

## 🤖 AI-Powered Features

### SEO Auto-Generation

Click **"Auto-Generate with AI"** to automatically create:

1. **Meta Description** - Compelling 150-160 character summary
2. **Meta Keywords** - Relevant SEO keywords
3. **Excerpt** - Brief preview text
4. **Suggested Tags** - Categorized labels
5. **Featured Images** - 6 curated Unsplash images

### Image Selection Gallery

After AI generation:
- View 6 image thumbnails
- First image is auto-selected
- Click any image to select it
- Images include Unsplash attribution

### Requirements for AI Features

Set these environment variables:

```bash
DEEPSEEK_API_KEY=your_deepseek_key
UNSPLASH_API_KEY=your_unsplash_key
```

---

## 📄 Document Import

Transform PDFs and DOCX files into complete blog articles.

### Supported Styles

| Style | Best For | Output |
|-------|----------|--------|
| **Investment Pitch** | Stock analyses | BUY/HOLD/SELL recommendation |
| **SEO Article** | General content | Web-optimized format |
| **Academic Paper** | Research reports | Formal structure |
| **Blog Post** | Casual content | Conversational style |

### Using Document Import

1. On **New Post** page, scroll to "AI-Powered Document Import"
2. Select your file (PDF, DOCX, or DOC)
3. Choose target style
4. Click **"Generate Article"**
5. Review and edit generated content
6. Select featured image
7. Save or publish

### Investment Pitch Style

Perfect for stock analyses, includes:

- **Executive Summary** - Core investment thesis
- **Business Overview** - Company description
- **Investment Case** - Bull case with data
- **Risk Factors** - Key risks
- **Valuation** - Target price and upside
- **Bottom Line** - BUY/HOLD/SELL recommendation

---

## 🎨 Writing Tips

### SEO-Friendly Titles

- Keep under 60 characters
- Include main keyword near beginning
- Be descriptive and compelling

✅ **Good:** "Bilibili Stock Analysis: Why BILI is a Hidden Gem"  
❌ **Bad:** "Stock Analysis" (too vague)

### Meta Descriptions

- 150-160 characters ideal
- Include call-to-action
- Mention key benefit/value

✅ **Good:** "Discover why Bilibili's undervalued stock presents a compelling investment opportunity with 40% upside potential."

### Using Tags Effectively

- Use 5-8 relevant tags
- Mix broad and specific: "stocks", "china", "tech", "bilibili"
- Include ticker symbols: "BILI", "TSLA"

### Featured Images

- Minimum 1200x630px for social sharing
- Use landscape orientation
- Choose professional, relevant images

---

## 🔒 Post Status

### Status Options

| Status | Visibility | Description |
|--------|------------|-------------|
| **Draft** | Only author | Work in progress |
| **Published** | Public | Live on blog |
| **Featured** | Public + Highlighted | Appears on homepage |

### Changing Status

1. Edit the post
2. Select status from dropdown
3. Save changes

**Note:** Only admins can mark posts as "Featured"

---

## 🔐 Security & Limits

### Rate Limiting

| Feature | Limit | Window |
|---------|-------|--------|
| SEO Generation | 20 requests | 1 hour |
| Image Search | 30 searches | 1 hour |
| Document Upload | 5 uploads | 1 hour |
| New Posts | 10 posts | 1 hour |

### File Upload Security

- **Max File Size:** 10MB
- **Allowed Types:** PDF, DOCX, DOC only
- **Validation:** File extension and MIME type checked
- **Storage:** Files processed temporarily, deleted after

---

## 🆘 Troubleshooting

**"No images found" Error**
- Try more generic search terms
- Check `UNSPLASH_API_KEY` is set correctly
- Unsplash may have limited results for specific queries

**Document Import Fails**
- Ensure file is under 10MB
- Check file is not password-protected
- Try converting to PDF if DOCX fails
- Ensure `DEEPSEEK_API_KEY` is configured

**SEO Generation Slow**
- Large documents (>4000 words) take longer
- AI generation typically takes 10-30 seconds
- If timeout, try with shorter content

**Changes Not Saving**
- Check title and content are not empty
- Ensure CSRF token is valid (refresh page)
- Check browser console for JavaScript errors

---

## 💡 Best Practices

### Content Quality

1. **Write for your audience** - Fellow investors and students
2. **Be factual** - Support claims with data
3. **Disclose conflicts** - Transparency builds trust
4. **Proofread** - Use AI as a starting point, not final

### SEO Optimization

1. **Use keywords naturally** - Don't keyword stuff
2. **Write compelling titles** - Click-worthy but accurate
3. **Add meta descriptions** - Improve search visibility
4. **Use headers (H2, H3)** - Structure your content

### Image Selection

1. **Choose relevant images** - Match your content
2. **Check licensing** - Unsplash images are free to use
3. **Optimize file size** - Faster page loads
4. **Include alt text** - Accessibility and SEO

---

## 📚 FAQ

**Q: Can I edit AI-generated content?**  
A: Yes! AI is a starting point. Always review and edit before publishing.

**Q: Are uploaded documents stored?**  
A: No. Documents are processed temporarily and deleted immediately.

**Q: Can I use the blog without AI features?**  
A: Yes. All AI features are optional. Write and publish manually.

**Q: Who can see my drafts?**  
A: Only you. Drafts are private until published.

**Q: How do I feature a post on the main page?**  
A: Admin users can mark posts as "Featured" in the post editor.

**Q: Can I schedule posts for later?**  
A: Currently, publish immediately or save as draft. Scheduled publishing coming soon.

---

<p align="center">
  <strong>Happy blogging!</strong><br>
  Share your investment insights with the community
</p>
