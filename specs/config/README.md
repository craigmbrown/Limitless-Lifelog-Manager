# Limitless Lifelog Configuration

This directory contains configuration files for customizing and tuning the Limitless Lifelog application.

## Keywords Configuration (keywords.json)

The `keywords.json` file controls how the application detects and categorizes different elements from transcripts. You can customize these keywords to better match your speech patterns and terminology.

### Configuration Sections

1. **Priority Keywords**
   - Controls how priority levels (high, medium, low) are determined
   - Add words you use to indicate importance or urgency

2. **Status Keywords**
   - Maps words to task status values (Not Started, In Progress, Completed)
   - Customize based on your terminology for task statuses

3. **Action Keywords**
   - Words that indicate actionable items in a transcript
   - Adding more specific verbs can improve task detection

4. **Project Category Keywords**
   - Used to automatically categorize tasks and projects
   - Add domain-specific terms for better project categorization

5. **Excluded Common Words**
   - Words to exclude from keyword extraction
   - Add common words from your domain that shouldn't be used as tags

6. **Date Keywords**
   - Terms used to identify date references in transcripts
   - Include domain-specific time references if needed

### Example Configuration

```json
{
  "priority_keywords": {
    "high": ["urgent", "critical", "important"],
    "medium": ["moderate", "soon"],
    "low": ["whenever", "sometime"]
  }
}
```

### How to Customize

1. Edit the `keywords.json` file directly to add or remove keywords
2. Keywords are case-insensitive during matching
3. You can group related terms (e.g., "high priority" and "top priority")
4. After changing keywords, restart the application for changes to take effect

## Best Practices

- Add domain-specific terminology to improve extraction quality
- Include variations of terms you commonly use
- Review excluded words periodically to ensure important terms aren't filtered
- When adding project categories, include clear distinctive keywords 
- Use the entire phrase for multi-word terms ("high priority" vs just "high")