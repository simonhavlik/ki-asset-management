"""
Presentation export routes for creating fiscal.ai-style charts and tables.
"""

import io
import base64
from datetime import datetime
from flask import Blueprint, render_template, send_file, request, flash, jsonify, redirect, url_for
from flask_login import login_required, current_user

from ..utils.presentation_export import (
    generate_all_presentation_exports,
    create_performance_chart,
    create_growth_chart,
    create_bar_chart,
    get_analyst_summary_table,
    get_sector_analysis,
    get_growth_timeline,
    generate_portfolio_chart_series
)

presentation_bp = Blueprint('presentation', __name__, url_prefix='/presentation')


def admin_required(f):
    """Decorator for admin-only routes."""
    from functools import wraps
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('Admin access required.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function


@presentation_bp.route('/')
@admin_required
def index():
    """Presentation exports dashboard."""
    return render_template('admin/presentation_exports.html')


@presentation_bp.route('/generate', methods=['POST'])
@admin_required
def generate():
    """Generate all presentation exports."""
    filter_type = request.form.get('filter_type', 'board_approved')
    high_resolution = request.form.get('high_resolution') == 'true'
    
    try:
        exports = generate_all_presentation_exports(filter_type, high_resolution=high_resolution)
        
        flash(f'Generated {len(exports["charts"])} charts and {len(exports["tables"])} tables in {exports.get("generation_time_seconds", 0):.1f}s', 'success')
        
        return render_template('admin/presentation_exports.html', 
                             exports=exports,
                             filter_type=filter_type,
                             high_resolution=high_resolution)
    except Exception as e:
        flash(f'Error generating exports: {str(e)}', 'danger')
        return render_template('admin/presentation_exports.html')


@presentation_bp.route('/chart/performance')
@admin_required
def chart_performance():
    """Download performance chart."""
    from ..models import Analysis, PortfolioPurchase
    
    filter_type = request.args.get('filter', 'board_approved')
    
    # Get analysis IDs
    if filter_type == 'purchased':
        purchases = PortfolioPurchase.query.all()
        analysis_ids = [p.analysis_id for p in purchases]
    elif filter_type == 'board_approved':
        analyses = Analysis.query.filter_by(board_status='Board Approved').all()
        analysis_ids = [a.id for a in analyses]
    elif filter_type == 'all_approved':
        analyses = Analysis.query.filter_by(status='On Watchlist').all()
        analysis_ids = [a.id for a in analyses]
    else:
        analyses = Analysis.query.all()
        analysis_ids = [a.id for a in analyses]
    
    series_data = generate_portfolio_chart_series(analysis_ids)
    
    if not series_data.get('dates'):
        flash('No data available for chart', 'warning')
        return redirect(url_for('presentation.index'))
    
    chart_bytes = create_performance_chart(
        series_data,
        title=f"KI AM Portfolio Performance ({filter_type.replace('_', ' ').title()})",
        width=14,
        height=7,
        dpi=200
    )
    
    return send_file(
        io.BytesIO(chart_bytes),
        mimetype='image/png',
        as_attachment=True,
        download_name=f'ki_performance_{filter_type}_{datetime.now().strftime("%Y%m%d")}.png'
    )


@presentation_bp.route('/chart/growth')
@admin_required
def chart_growth():
    """Download growth timeline chart."""
    timeline_data = get_growth_timeline()
    
    if not timeline_data.get('dates'):
        flash('No timeline data available', 'warning')
        return redirect(url_for('presentation.index'))
    
    chart_bytes = create_growth_chart(
        timeline_data,
        width=14,
        height=7,
        dpi=200
    )
    
    return send_file(
        io.BytesIO(chart_bytes),
        mimetype='image/png',
        as_attachment=True,
        download_name=f'ki_growth_timeline_{datetime.now().strftime("%Y%m%d")}.png'
    )


@presentation_bp.route('/chart/sectors')
@admin_required
def chart_sectors():
    """Download sector performance chart."""
    sector_data = get_sector_analysis()
    
    if not sector_data['best_sectors']['rows']:
        flash('No sector data available', 'warning')
        return redirect(url_for('presentation.index'))
    
    chart_bytes = create_bar_chart(
        sector_data['best_sectors']['rows'][:10],
        'avg_return', 'sector',
        'Top Sectors by Average Return',
        color='#10b981',
        horizontal=True,
        width=12,
        height=8,
        dpi=200
    )
    
    return send_file(
        io.BytesIO(chart_bytes),
        mimetype='image/png',
        as_attachment=True,
        download_name=f'ki_sectors_{datetime.now().strftime("%Y%m%d")}.png'
    )


@presentation_bp.route('/data/analysts')
@admin_required
def data_analysts():
    """Get analyst summary data as JSON."""
    data = get_analyst_summary_table()
    return jsonify(data)


@presentation_bp.route('/data/sectors')
@admin_required
def data_sectors():
    """Get sector analysis data as JSON."""
    data = get_sector_analysis()
    return jsonify(data)


@presentation_bp.route('/data/timeline')
@admin_required
def data_timeline():
    """Get growth timeline data as JSON."""
    data = get_growth_timeline()
    return jsonify(data)


@presentation_bp.route('/refresh-cache', methods=['POST'])
@admin_required
def refresh_cache():
    """Manually trigger cache refresh."""
    from ..scheduler import refresh_all_cached_data
    
    try:
        refresh_all_cached_data()
        flash('Cache refreshed successfully!', 'success')
    except Exception as e:
        flash(f'Error refreshing cache: {str(e)}', 'danger')
    
    return redirect(url_for('presentation.index'))


@presentation_bp.route('/download/all')
@admin_required
def download_all():
    """Download all charts as a zip file."""
    import zipfile
    
    filter_type = request.args.get('filter', 'board_approved')
    
    # Generate all charts
    exports = generate_all_presentation_exports(filter_type)
    
    # Create zip file in memory
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Add charts
        for chart_name, chart_b64 in exports.get('charts', {}).items():
            chart_bytes = base64.b64decode(chart_b64)
            zip_file.writestr(f'{chart_name}.png', chart_bytes)
        
        # Add JSON data
        import json
        zip_file.writestr('tables/analysts.json', json.dumps(exports.get('tables', {}).get('analysts', {}), indent=2))
        zip_file.writestr('tables/best_sectors.json', json.dumps(exports.get('tables', {}).get('best_sectors', {}), indent=2))
        zip_file.writestr('tables/risk_sectors.json', json.dumps(exports.get('tables', {}).get('risk_sectors', {}), indent=2))
    
    zip_buffer.seek(0)
    
    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'ki_presentation_exports_{datetime.now().strftime("%Y%m%d_%H%M")}.zip'
    )
