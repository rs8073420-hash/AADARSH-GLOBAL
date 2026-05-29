import os
import shutil
import uuid
from flask import Blueprint, request, jsonify, current_app, send_file
from flask_jwt_extended import get_jwt_identity
from werkzeug.utils import secure_filename
from ..models.attachment import AttachmentModel
from ..middleware.auth_middleware import employee_required
from bson import ObjectId

attachments_bp = Blueprint('attachments', __name__)

# Constants for limits (in bytes)
SIZE_LIMITS = {
    'image': 5 * 1024 * 1024,      # 5 MB
    'document': 10 * 1024 * 1024,  # 10 MB (PDF, DOCX)
    'excel': 10 * 1024 * 1024,     # 10 MB
    'zip': 20 * 1024 * 1024,       # 20 MB
    'video': 25 * 1024 * 1024,     # 25 MB
    'default': 5 * 1024 * 1024     # 5 MB fallback
}

ALLOWED_EXTENSIONS = {
    'image': {'png', 'jpg', 'jpeg', 'gif', 'webp'},
    'document': {'pdf', 'doc', 'docx', 'txt'},
    'excel': {'xls', 'xlsx', 'csv'},
    'zip': {'zip', 'rar', '7z'},
    'video': {'mp4', 'webm', 'ogg'}
}

def get_file_category(ext):
    ext = ext.lower()
    for cat, exts in ALLOWED_EXTENSIONS.items():
        if ext in exts:
            return cat
    return None

def get_upload_paths():
    base_dir = os.path.join(current_app.root_path, 'uploads')
    temp_dir = os.path.join(base_dir, 'temp')
    paths = {
        'temp': temp_dir,
        'image': os.path.join(base_dir, 'images'),
        'document': os.path.join(base_dir, 'documents'),
        'excel': os.path.join(base_dir, 'excel'),
        'zip': os.path.join(base_dir, 'zips'),
        'video': os.path.join(base_dir, 'videos'),
        'other': os.path.join(base_dir, 'other')
    }
    for p in paths.values():
        os.makedirs(p, exist_ok=True)
    return paths

@attachments_bp.route('/upload_chunk', methods=['POST'])
@employee_required
def upload_chunk():
    """Receives a file chunk and appends it to a temporary file."""
    upload_id = request.form.get('upload_id')
    chunk_index = int(request.form.get('chunk_index', 0))
    file_obj = request.files.get('file')
    
    if not upload_id or not file_obj:
        return jsonify({'error': 'Missing upload_id or file data'}), 400
        
    paths = get_upload_paths()
    temp_path = os.path.join(paths['temp'], f"{secure_filename(upload_id)}.part")
    
    # Append the chunk to the file
    mode = 'ab' if chunk_index > 0 else 'wb'
    with open(temp_path, mode) as f:
        file_obj.save(f)
        
    return jsonify({'success': True}), 200

@attachments_bp.route('/upload_complete', methods=['POST'])
@employee_required
def upload_complete():
    """Validates the completed file, moves it to permanent storage, and creates DB record."""
    identity = get_jwt_identity()
    data = request.get_json()
    
    upload_id = data.get('upload_id')
    original_filename = data.get('file_name')
    room_id = data.get('room_id')
    
    if not upload_id or not original_filename:
        return jsonify({'error': 'Missing upload_id or file_name'}), 400
        
    paths = get_upload_paths()
    temp_path = os.path.join(paths['temp'], f"{secure_filename(upload_id)}.part")
    
    if not os.path.exists(temp_path):
        return jsonify({'error': 'Upload file not found'}), 404
        
    # Security checks
    file_size = os.path.getsize(temp_path)
    ext = original_filename.rsplit('.', 1)[-1].lower() if '.' in original_filename else ''
    
    if ext in {'exe', 'bat', 'sh', 'php', 'js', 'html'}:
        os.remove(temp_path)
        return jsonify({'error': 'Executable files are not allowed'}), 400
        
    category = get_file_category(ext) or 'other'
    max_size = SIZE_LIMITS.get(category, SIZE_LIMITS['default'])
    
    if file_size > max_size:
        os.remove(temp_path)
        return jsonify({'error': f'File exceeds {max_size//(1024*1024)}MB limit for this file type.'}), 400
        
    # Generate safe filename and move to permanent storage
    safe_name = f"{uuid.uuid4().hex}_{secure_filename(original_filename)}"
    dest_dir = paths.get(category, paths['other'])
    final_path = os.path.join(dest_dir, safe_name)
    
    shutil.move(temp_path, final_path)
    
    # Save to MongoDB
    model = AttachmentModel()
    attachment_data = {
        'room_id': room_id,
        'sender_id': identity,
        'file_name': original_filename,
        'file_type': ext,
        'file_size': file_size,
        'file_path': final_path
    }
    
    result = model.create(attachment_data)
    
    return jsonify({
        'success': True,
        'attachment': {
            '_id': str(result.inserted_id),
            'file_name': original_filename,
            'file_type': ext,
            'file_size': file_size
        }
    }), 201

@attachments_bp.route('/download/<attachment_id>', methods=['GET'])
@employee_required
def download_file(attachment_id):
    """Streams the requested file to the client."""
    model = AttachmentModel()
    attachment = model.get_by_id(attachment_id)
    
    if not attachment:
        return jsonify({'error': 'File not found'}), 404
        
    file_path = attachment.get('file_path')
    if not file_path or not os.path.exists(file_path):
        return jsonify({'error': 'Physical file missing'}), 404
        
    # send_file uses Werkzeug's optimized wsgi file wrapper to stream efficiently
    return send_file(
        file_path, 
        as_attachment=True, 
        download_name=attachment.get('file_name', 'downloaded_file')
    )

@attachments_bp.route('/preview/<attachment_id>', methods=['GET'])
@employee_required
def preview_file(attachment_id):
    """Returns the file inline (for images/PDF previews)."""
    model = AttachmentModel()
    attachment = model.get_by_id(attachment_id)
    
    if not attachment:
        return jsonify({'error': 'File not found'}), 404
        
    file_path = attachment.get('file_path')
    if not file_path or not os.path.exists(file_path):
        return jsonify({'error': 'Physical file missing'}), 404
        
    return send_file(file_path, as_attachment=False)
