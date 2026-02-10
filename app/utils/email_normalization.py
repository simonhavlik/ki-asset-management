"""
Email normalization utilities for analyst website.
Strip diacritics and ensure consistent email format.
"""
import unicodedata
import re


def normalize_email(email: str) -> str:
    """
    Normalize an email address by:
    1. Converting to lowercase.
    2. Stripping diacritics (accents) from the local part (before '@').
    3. Keeping the domain part unchanged.
    
    Example:
        'József.Kovács@example.com' -> 'jozsef.kovacs@example.com'
        'müller.josé@example.com' -> 'muller.jose@example.com'
    
    If the email does not contain '@', the whole string is normalized.
    """
    if not email:
        return email
    # Lowercase entire email
    email = email.lower()
    # Split local part and domain
    parts = email.split('@', 1)
    local_part = parts[0]
    if len(parts) == 2:
        domain = parts[1]
    else:
        domain = ''
    # Normalize local part: remove diacritics and replace non-ASCII characters
    # Using NFKD decomposition and filtering out combining characters
    normalized = unicodedata.normalize('NFKD', local_part)
    stripped = ''.join(c for c in normalized if not unicodedata.combining(c))
    # Ensure only ASCII letters, digits, dots, underscores, hyphens? keep as is.
    # If after stripping there are still non-ASCII characters, replace them with ASCII approximations?
    # For simplicity, we'll just keep stripped as is; it should be ASCII.
    local_part = stripped
    if domain:
        return f'{local_part}@{domain}'
    else:
        return local_part


def normalize_name_for_email(name: str) -> str:
    """
    Normalize a person's name for deriving email local part.
    Converts to lowercase, strips diacritics, replaces spaces with dots.
    """
    if not name:
        return ''
    # Lowercase
    name = name.lower()
    # Strip diacritics
    normalized = unicodedata.normalize('NFKD', name)
    stripped = ''.join(c for c in normalized if not unicodedata.combining(c))
    # Replace spaces with dots
    stripped = stripped.replace(' ', '.')
    # Remove any characters that are not allowed in email local part
    # Keep letters, digits, dots, hyphens, underscores
    stripped = re.sub(r'[^a-z0-9._-]', '', stripped)
    return stripped


if __name__ == '__main__':
    # Quick test
    test_emails = [
        'josé.garcía@example.com',
        'François.Müller@example.com',
        'příliš.žluťoučký@example.com',
        'normal@example.com',
        'noatsign',
        ''
    ]
    for e in test_emails:
        print(f'{e!r} -> {normalize_email(e)!r}')
    test_names = ['José García', 'François Müller', 'Příliš Žluťoučký']
    for n in test_names:
        print(f'{n!r} -> {normalize_name_for_email(n)!r}')