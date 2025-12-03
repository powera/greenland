#!/usr/bin/python3

"""Routes for data export functionality (POVAS HTML generation and UNGURYS WireWord exports)."""

from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, send_file
import subprocess
import os
import re
from pathlib import Path
from config import Config

bp = Blueprint("exports", __name__, url_prefix="/exports")


@bp.route("/")
def exports_page():
    """Display the exports landing page with POVAS and UNGURYS options."""
    return render_template("exports/index.html")


@bp.route("/povas")
def povas_form():
    """Display the POVAS HTML generation form."""
    return render_template("exports/povas.html")


@bp.route("/povas/generate", methods=["POST"])
def povas_generate():
    """Execute POVAS to generate HTML files."""
    generation_mode = request.form.get("generation_mode", "all")  # 'all' or 'index-only'
    dry_run = request.form.get("dry_run") == "true"

    # Build command
    agents_dir = Path(Config.DB_PATH).parent.parent / "agents"
    script_path = agents_dir / "povas.py"

    if not script_path.exists():
        return jsonify({"success": False, "error": f"Script not found: {script_path}"}), 404

    # Build arguments
    args = ["python3", str(script_path)]

    if generation_mode == "index-only":
        args.append("--index-only")

    if dry_run:
        args.append("--dry-run")

    # Add database path
    args.extend(["--db-path", Config.DB_PATH])

    try:
        # Execute
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        stdout, stderr = process.communicate(timeout=300)  # 5 min timeout

        success = process.returncode == 0

        return jsonify(
            {
                "success": success,
                "stdout": stdout,
                "stderr": stderr,
                "returncode": process.returncode,
            }
        )

    except subprocess.TimeoutExpired:
        process.kill()
        return (
            jsonify(
                {"success": False, "error": "Generation timed out (5 minutes)", "timeout": True}
            ),
            408,
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/elnias")
def elnias_form():
    """Display the ELNIAS bootstrap export form."""
    return render_template("exports/elnias.html")


@bp.route("/elnias/generate", methods=["POST"])
def elnias_generate():
    """Execute ELNIAS to generate bootstrap JSON file."""
    language = request.form.get("language", "lt")
    include_unverified = request.form.get("include_unverified") == "true"

    # Build command
    agents_dir = Path(Config.DB_PATH).parent.parent / "agents"
    script_path = agents_dir / "elnias.py"

    if not script_path.exists():
        return jsonify({"success": False, "error": f"Script not found: {script_path}"}), 404

    # Build arguments
    args = ["python3", str(script_path)]

    # Add language
    args.extend(["--language", language])

    # Add include-unverified flag if checked
    if include_unverified:
        args.append("--include-unverified")

    # Add database path
    args.extend(["--db-path", Config.DB_PATH])

    try:
        # Execute
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        stdout, stderr = process.communicate(timeout=300)  # 5 min timeout

        success = process.returncode == 0

        # Parse the output to extract the file path
        output_path = None
        if success and stdout:
            # Look for "Successfully wrote X entries to /path/to/file" in stdout
            match = re.search(r"Successfully wrote \d+ entries to (.+)", stdout)
            if match:
                output_path = match.group(1).strip()

        response_data = {
            "success": success,
            "stdout": stdout,
            "stderr": stderr,
            "returncode": process.returncode,
        }

        if output_path:
            response_data["output_path"] = output_path

        return jsonify(response_data)

    except subprocess.TimeoutExpired:
        process.kill()
        return (
            jsonify(
                {"success": False, "error": "Generation timed out (5 minutes)", "timeout": True}
            ),
            408,
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/elnias/download")
def elnias_download():
    """Download the generated ELNIAS bootstrap file."""
    file_path = request.args.get("path")

    if not file_path:
        flash("No file path provided", "error")
        return redirect(url_for("exports.elnias_form"))

    # Security: Ensure the file path is within the project directory
    project_root = Path(Config.DB_PATH).parent.parent
    abs_file_path = Path(file_path).resolve()

    try:
        # Check if file is within project root
        abs_file_path.relative_to(project_root)
    except ValueError:
        flash("Invalid file path", "error")
        return redirect(url_for("exports.elnias_form"))

    if not abs_file_path.exists():
        flash("File not found", "error")
        return redirect(url_for("exports.elnias_form"))

    return send_file(
        abs_file_path,
        as_attachment=True,
        download_name=abs_file_path.name,
        mimetype="application/json",
    )
