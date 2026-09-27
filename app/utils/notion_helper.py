"""
Notion API integration for CSV import.

This module provides functionality to query Notion databases directly
and convert the results to CSV format for import.
"""

import csv
import io
import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any, List

import requests

logger = logging.getLogger(__name__)


class NotionAPIError(Exception):
    """Custom exception for Notion API errors."""
    pass


def extract_property_value(prop: Dict) -> str:
    """Extract plain text value from a Notion property."""
    if prop is None:
        return ""

    prop_type = prop.get('type', '')

    if prop_type == 'title':
        title_list = prop.get('title', [])
        return ''.join(t.get('plain_text', '') for t in title_list)

    elif prop_type == 'rich_text':
        rich_list = prop.get('rich_text', [])
        return ''.join(t.get('plain_text', '') for t in rich_list)

    elif prop_type == 'number':
        return str(prop.get('number', '') or '')

    elif prop_type == 'select':
        select_val = prop.get('select')
        return select_val.get('name', '') if select_val else ''

    elif prop_type == 'multi_select':
        multi = prop.get('multi_select', [])
        return ', '.join(s.get('name', '') for s in multi)

    elif prop_type == 'date':
        date_val = prop.get('date')
        return date_val.get('start', '') if date_val else ''

    elif prop_type == 'checkbox':
        return 'Yes' if prop.get('checkbox') else 'No'

    elif prop_type == 'url':
        return prop.get('url', '') or ''

    elif prop_type == 'email':
        return prop.get('email', '') or ''

    elif prop_type == 'phone_number':
        return prop.get('phone_number', '') or ''

    elif prop_type == 'people':
        people = prop.get('people', [])
        return ', '.join(p.get('name', '') for p in people if p.get('name'))

    elif prop_type == 'files':
        files = prop.get('files', [])
        return ', '.join(f.get('name', '') for f in files if f.get('name'))

    else:
        return ""


def convert_notion_to_csv(pages: List[Dict], column_mapping: Dict[str, str]) -> str:
    """
    Convert Notion pages to CSV format.

    Args:
        pages: List of Notion page objects
        column_mapping: Maps Notion property names to CSV column names

    Returns:
        CSV content as string
    """
    if not pages:
        return ""

    output = io.StringIO()
    writer = csv.writer(output)

    csv_headers = list(column_mapping.values())
    writer.writerow(csv_headers)

    for page in pages:
        properties = page.get('properties', {})

        row = []
        for notion_prop, csv_col in column_mapping.items():
            if notion_prop in properties:
                value = extract_property_value(properties[notion_prop])
            else:
                value = ""
            row.append(value)

        writer.writerow(row)

    return output.getvalue()


class NotionClient:
    """
    Client for interacting with Notion API to download database content.

    Requires a Notion integration token with access to the database.
    """

    def __init__(self, api_key: str):
        """
        Initialize the Notion client.

        Args:
            api_key: Notion integration token (API key)
        """
        self.api_key = api_key
        self.base_url = "https://api.notion.com/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }

    def query_database(self, database_id: str, page_size: int = 100) -> List[Dict]:
        """
        Query all pages in a Notion database.

        Args:
            database_id: The Notion database ID
            page_size: Number of results per page (max 100)

        Returns:
            List of page objects
        """
        all_results = []
        url = f"{self.base_url}/databases/{database_id}/query"
        has_more = True
        next_cursor = None

        while has_more:
            payload = {"page_size": min(page_size, 100)}
            if next_cursor:
                payload["start_cursor"] = next_cursor

            try:
                response = requests.post(url, headers=self.headers, json=payload, timeout=30)

                if response.status_code == 401:
                    raise NotionAPIError("Invalid or expired Notion API key")
                elif response.status_code == 404:
                    raise NotionAPIError(f"Database {database_id} not found or access denied")
                elif response.status_code != 200:
                    raise NotionAPIError(f"Notion API error: {response.status_code}")

                data = response.json()
                all_results.extend(data.get('results', []))
                has_more = data.get('has_more', False)
                next_cursor = data.get('next_cursor')

                if has_more:
                    logger.info(f"Fetching more pages... ({len(all_results)} so far)")
                    time.sleep(0.5)

            except requests.exceptions.RequestException as e:
                raise NotionAPIError(f"Network error: {str(e)}")

        return all_results

    def get_database_info(self, database_id: str) -> Dict[str, Any]:
        """
        Get information about a Notion database.

        Args:
            database_id: The Notion database ID

        Returns:
            Dict with database metadata
        """
        url = f"{self.base_url}/databases/{database_id}"

        try:
            response = requests.get(url, headers=self.headers, timeout=30)

            if response.status_code == 401:
                raise NotionAPIError("Invalid or expired Notion API key")
            elif response.status_code == 404:
                raise NotionAPIError(f"Database {database_id} not found")
            elif response.status_code != 200:
                raise NotionAPIError(f"Notion API error: {response.status_code}")

            db = response.json()

            title = "Untitled"
            if db.get('title') and len(db.get('title', [])) > 0:
                title = db['title'][0].get('plain_text', 'Untitled')

            properties = db.get('properties', {})
            prop_list = [{'name': name, 'type': info.get('type', 'unknown')} for name, info in properties.items()]

            return {
                'id': database_id,
                'title': title,
                'properties': prop_list,
                'url': f"https://www.notion.so/{database_id.replace('-', '')}"
            }

        except requests.exceptions.RequestException as e:
            raise NotionAPIError(f"Failed to get database info: {str(e)}")

    def get_database_properties(self, database_id: str) -> Dict[str, Any]:
        """Return the raw property specs for a database, as {name: spec}.

        auto_detect_column_mapping() needs the full spec (including each
        property's type), which get_database_info() deliberately reduces away.
        Read-only: a single GET, no writes.
        """
        url = f"{self.base_url}/databases/{database_id}"
        response = requests.get(url, headers=self.headers, timeout=30)

        if response.status_code == 401:
            raise NotionAPIError("Invalid or expired Notion API key")
        if response.status_code == 404:
            raise NotionAPIError(f"Database {database_id} not found or access denied")
        if response.status_code != 200:
            raise NotionAPIError(f"Notion API error: {response.status_code}")

        return response.json().get('properties', {})

    def export_database_as_csv(self, database_id: str, column_mapping: Dict[str, str]) -> str:
        """
        Export a Notion database as CSV content.

        Args:
            database_id: The Notion database ID
            column_mapping: Maps Notion property names to CSV column names

        Returns:
            CSV content as string
        """
        logger.info(f"Querying Notion database: {database_id}")

        pages = self.query_database(database_id)

        if not pages:
            logger.warning("No pages found in database")
            return ""

        logger.info(f"Found {len(pages)} pages in database")

        csv_content = convert_notion_to_csv(pages, column_mapping)

        return csv_content


def download_notion_export(database_id: str, api_key: Optional[str] = None,
                            column_mapping: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    Convenience function to download a Notion database as CSV.

    Args:
        database_id: The Notion database ID
        api_key: Optional API key (will use NOTION_API_KEY env var if not provided)
        column_mapping: Optional mapping of Notion property names to CSV column names

    Returns:
        Dict with export details including csv_content
    """
    import os

    if api_key is None:
        api_key = os.environ.get('NOTION_API_KEY', '')

    if not api_key:
        raise NotionAPIError("Notion API key not configured. Set NOTION_API_KEY environment variable.")

    # Note: a hardcoded default mapping used to live here. It broke against the
    # real database, whose title column is 'Name' (not 'Company') and whose date
    # column is 'Date ' with a trailing space. The result was a CSV of blanks that
    # imported as 0 rows while still reporting success. When column_mapping is
    # None we now auto-detect from the database's real property names instead.
    client = NotionClient(api_key)

    try:
        db_info = client.get_database_info(database_id)
        logger.info(f"Connected to Notion database: {db_info['title']}")

        if column_mapping is None:
            properties = client.get_database_properties(database_id)
            column_mapping = build_notion_column_mapping(properties)
            resolved = {prop.strip() or prop: col for prop, col in column_mapping.items()}
            logger.info(f"Auto-detected Notion column mapping: {resolved}")
            missing = [col for prop, col in column_mapping.items() if prop.startswith('__missing__')]
            if missing:
                logger.warning(
                    "Notion database has no property for CSV column(s): %s - "
                    "those columns will be empty",
                    ', '.join(missing),
                )

        csv_content = client.export_database_as_csv(database_id, column_mapping)

        return {
            'success': True,
            'csv_content': csv_content,
            'database_id': database_id,
            'database_name': db_info['title'],
            'column_mapping': column_mapping,
            'page_count': len(csv_content.split('\n')) - 1 if csv_content else 0
        }

    except NotionAPIError:
        raise
    except Exception as e:
        logger.error(f"Notion export failed: {e}")
        raise NotionAPIError(str(e))


def auto_detect_column_mapping(properties: Dict[str, Any]) -> Dict[str, str]:
    """
    Automatically detect column mapping based on Notion property names.

    Args:
        properties: Notion database properties

    Returns:
        Mapping from Notion property names to CSV column names
    """
    mapping = {}
    csv_columns = ['Company', 'Date', 'Sector', 'Analyst', 'Opponent', 'Comment', 'Status', 'Files & media']

    for csv_col in csv_columns:
        csv_col_lower = csv_col.lower()

        for notion_prop, prop_info in properties.items():
            # Strip whitespace before comparing: real databases contain property
            # names such as 'Date ' (trailing space), and an exact match on
            # 'date' silently fails against them.
            notion_lower = notion_prop.strip().lower()

            if csv_col_lower == 'company':
                if notion_lower in ['company', 'ticker', 'name', 'title', 'security', 'asset']:
                    if prop_info.get('type') == 'title':
                        mapping[notion_prop] = csv_col
                        break
            elif csv_col_lower == 'date':
                if notion_lower in ['date', 'analysis date', 'report date', 'publish date', 'datum']:
                    mapping[notion_prop] = csv_col
                    break
            elif csv_col_lower == 'sector':
                if notion_lower in ['sector', 'industry', 'category', 'třída', 'sektor']:
                    mapping[notion_prop] = csv_col
                    break
            elif csv_col_lower == 'analyst':
                if notion_lower in ['analyst', 'author', 'owner', 'created by', 'prepared by']:
                    if prop_info.get('type') in ['people', 'rich_text']:
                        mapping[notion_prop] = csv_col
                        break
            elif csv_col_lower == 'opponent':
                if notion_lower in ['opponent', 'peer', 'competition', 'competitor', 'protistrana']:
                    mapping[notion_prop] = csv_col
                    break
            elif csv_col_lower == 'comment':
                if notion_lower in ['comment', 'comments', 'note', 'notes', 'description', 'voting', 'poznámka']:
                    if prop_info.get('type') in ['rich_text', 'text']:
                        mapping[notion_prop] = csv_col
                        break
            elif csv_col_lower == 'status':
                if notion_lower in ['status', 'state', 'phase', 'progress', 'stav']:
                    if prop_info.get('type') == 'select':
                        mapping[notion_prop] = csv_col
                        break
            elif csv_col_lower == 'files & media':
                if notion_lower in ['files', 'file', 'media', 'attachment', 'attachments', 'files & media']:
                    if prop_info.get('type') == 'files':
                        mapping[notion_prop] = csv_col
                        break

    return mapping


# The CSV columns CsvImporter requires. The importer raises if any are absent,
# so the mapping always provides all of them.
NOTION_CSV_COLUMNS = [
    'Company', 'Date', 'Sector', 'Analyst', 'Opponent', 'Comment', 'Status', 'Files & media'
]


def build_notion_column_mapping(properties: Dict[str, Any]) -> Dict[str, str]:
    """Build a complete Notion-property -> CSV-column mapping for a database.

    This is the mapping the importer should use instead of a hardcoded one. It
    auto-detects each column from the database's real property names (via
    auto_detect_column_mapping, which ignores surrounding whitespace).

    Any CSV column with no matching property is mapped from a placeholder key
    that cannot exist in the database. That keeps the output CSV carrying every
    header CsvImporter expects, with an empty value for the columns the database
    genuinely does not have (e.g. 'Files & media').

    Returns:
        Dict mapping the Notion property name to the CSV column name.
    """
    by_csv = {csv_col: notion_prop for notion_prop, csv_col in auto_detect_column_mapping(properties).items()}

    mapping: Dict[str, str] = {}
    used: set = set()
    for column in NOTION_CSV_COLUMNS:
        notion_prop = by_csv.get(column)
        if notion_prop is None or notion_prop in used:
            notion_prop = f'__missing__{column}'
            while notion_prop in properties or notion_prop in used:
                notion_prop += '_'
        used.add(notion_prop)
        mapping[notion_prop] = column

    return mapping
