#!/usr/bin/python3

"""Routes for viewing operation logs."""

from flask import Blueprint, render_template, request, g
import json

from wordfreq.storage.models.operation_log import OperationLog
from wordfreq.storage.models.schema import Lemma
from config import Config

bp = Blueprint('operation_logs', __name__, url_prefix='/logs')


@bp.route('/')
def list_logs():
    """List operation logs with pagination and filtering."""
    page = request.args.get('page', 1, type=int)
    source_filter = request.args.get('source', '').strip()
    operation_type_filter = request.args.get('operation_type', '').strip()
    lemma_id_filter = request.args.get('lemma_id', '', type=str).strip()

    # Build query
    query = g.db.query(OperationLog)

    # Apply filters
    if source_filter:
        query = query.filter(OperationLog.source == source_filter)

    if operation_type_filter:
        query = query.filter(OperationLog.operation_type == operation_type_filter)

    if lemma_id_filter:
        try:
            lemma_id = int(lemma_id_filter)
            query = query.filter(OperationLog.lemma_id == lemma_id)
        except ValueError:
            pass

    # Order by most recent first
    query = query.order_by(OperationLog.timestamp.desc())

    # Paginate
    total = query.count()
    logs = query.limit(Config.ITEMS_PER_PAGE).offset((page - 1) * Config.ITEMS_PER_PAGE).all()

    # Parse JSON facts and enrich with lemma info
    enriched_logs = []
    for log in logs:
        try:
            fact_data = json.loads(log.fact)
        except json.JSONDecodeError:
            fact_data = {'error': 'Invalid JSON'}

        lemma = None
        if log.lemma_id:
            lemma = g.db.query(Lemma).get(log.lemma_id)

        enriched_logs.append({
            'log': log,
            'fact_data': fact_data,
            'lemma': lemma
        })

    # Get unique sources and operation types for filters
    sources = g.db.query(OperationLog.source).distinct().order_by(OperationLog.source).all()
    sources = [s[0] for s in sources if s[0]]

    operation_types = g.db.query(OperationLog.operation_type).distinct().order_by(OperationLog.operation_type).all()
    operation_types = [o[0] for o in operation_types if o[0]]

    # Calculate pagination
    total_pages = (total + Config.ITEMS_PER_PAGE - 1) // Config.ITEMS_PER_PAGE

    return render_template('logs/list.html',
                         logs=enriched_logs,
                         page=page,
                         total_pages=total_pages,
                         total=total,
                         source_filter=source_filter,
                         operation_type_filter=operation_type_filter,
                         lemma_id_filter=lemma_id_filter,
                         sources=sources,
                         operation_types=operation_types)


@bp.route('/<int:log_id>')
def view_log(log_id):
    """View a single operation log entry."""
    log = g.db.query(OperationLog).get(log_id)
    if not log:
        from flask import flash, redirect, url_for
        flash('Log entry not found', 'error')
        return redirect(url_for('operation_logs.list_logs'))

    try:
        fact_data = json.loads(log.fact)
    except json.JSONDecodeError:
        fact_data = {'error': 'Invalid JSON'}

    lemma = None
    if log.lemma_id:
        lemma = g.db.query(Lemma).get(log.lemma_id)

    return render_template('logs/view.html',
                         log=log,
                         fact_data=fact_data,
                         lemma=lemma)
