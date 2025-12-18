from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import subprocess
import tempfile
from scad_generator import generate_scad_script
import logging

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEMP_DIR = tempfile.gettempdir()
os.makedirs(TEMP_DIR, exist_ok=True)

@app.route('/health', methods=['GET'])
def health_check():
    try:
        result = subprocess.run(['which', 'openscad'], 
                              capture_output=True, 
                              text=True, 
                              timeout=5)
        if result.returncode == 0:
            openscad_path = result.stdout.strip()
            version_result = subprocess.run(['openscad', '--version'], 
                                          capture_output=True, 
                                          text=True, 
                                          timeout=5,
                                          env={'DISPLAY': ':99'})
            version_info = version_result.stdout.strip() or version_result.stderr.strip() or "Installed"
            openscad_status = f"{openscad_path} - {version_info}"
        else:
            openscad_status = "Not found"
    except Exception as e:
        openscad_status = f"Error: {str(e)}"
    
    return jsonify({
        'status': 'healthy',
        'openscad': openscad_status,
        'temp_dir': TEMP_DIR
    })

def get_available_fonts():
    try:
        result = subprocess.run(
            ['fc-list'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return set()
        
        font_families = set()
        for line in result.stdout.strip().split('\n'):
            if line and ':' in line:
                parts = line.split(':', 1)
                if len(parts) >= 2:
                    font_info = parts[1].strip()
                    
                    if ':style=' in font_info:
                        font_name = font_info.split(':style=')[0].strip()
                    else:
                        font_name = font_info.strip()
                    
                    for name in font_name.split(','):
                        clean_name = name.strip()
                        if clean_name:
                            font_families.add(clean_name)
        
        return font_families
        
    except Exception as e:
        logger.error(f"Error getting available fonts: {e}")
        return set()

def validate_font(font_name):
    logger.info(f"Validating font: {font_name}")
    
    available_fonts = get_available_fonts()
    
    if not available_fonts:
        logger.error("Could not retrieve font list from system")
        raise ValueError("Cannot get system fonts")
    
    if font_name not in available_fonts:
        logger.error(f"Font '{font_name}' not found in system. Available fonts: {len(available_fonts)}")
        raise ValueError(f"Font '{font_name}' not found")
    
    logger.info(f"Font '{font_name}' validated successfully")
    return font_name

@app.route('/list-fonts', methods=['GET'])
def list_fonts():
    try:
        result = subprocess.run(
            ['fc-list'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            logger.error(f"fc-list failed: {result.stderr}")
            return jsonify({'error': 'Failed to list fonts'}), 500
        
        font_families = set()
        for line in result.stdout.strip().split('\n'):
            if line and ':' in line:
                parts = line.split(':', 1)
                if len(parts) >= 2:
                    font_info = parts[1].strip()
                    
                    if ':style=' in font_info:
                        font_name = font_info.split(':style=')[0].strip()
                    else:
                        font_name = font_info.strip()
                    
                    for family in font_name.split(','):
                        clean_name = family.strip()
                        if clean_name:
                            font_families.add(clean_name)
        
        sorted_fonts = sorted(font_families)
        logger.info(f"Found {len(sorted_fonts)} unique font families")
        
        return jsonify({
            'fonts': sorted_fonts,
            'total': len(sorted_fonts)
        })
        
    except Exception as e:
        logger.error(f"Error in list_fonts: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/generate', methods=['POST'])
def generate_stl():
    try:
        data = request.json
        logger.info(f"Received request: {data}")
        
        letter1 = data.get('letter1', 'D')
        letter2 = data.get('letter2', 'T')
        font1 = data.get('font1', 'Roboto')
        font2 = data.get('font2', 'Roboto')
        size = data.get('size', 20)
        
        # Support multiple parameter formats
        if 'bailRelativeX' in data:
            # New format (relative vector)
            bailRelativeX = data.get('bailRelativeX', 0)
            bailRelativeY = data.get('bailRelativeY', 0)
            bailRelativeZ = data.get('bailRelativeZ', 0)
            bailRotation = data.get('bailRotation', 0)
        elif 'bailX' in data:
            # Old flat format
            bailRelativeX = data.get('bailX', 0)
            bailRelativeY = data.get('bailY', 0)
            bailRelativeZ = data.get('bailZ', 0)
            bailRotation = data.get('bailRotation', 0)
        else:
            # Nested format (oldest)
            pendant_config = data.get('pendant', {})
            bailRelativeX = pendant_config.get('x', 0)
            bailRelativeY = pendant_config.get('y', 0)
            bailRelativeZ = pendant_config.get('z', 0)
            bailRotation = pendant_config.get('rotation_y', 0)
        
        logger.info(f"Bail params: X={bailRelativeX}, Y={bailRelativeY}, Z={bailRelativeZ}, Rotation={bailRotation}")
        
        font1 = validate_font(font1)
        font2 = validate_font(font2)
        
        scad_content = generate_scad_script(
            letter1=letter1,
            letter2=letter2,
            font1=font1,
            font2=font2,
            size=size,
            bailRelativeX=bailRelativeX,
            bailRelativeY=bailRelativeY,
            bailRelativeZ=bailRelativeZ,
            bailRotation=bailRotation
        )
        
        if 'rotate([0, 0, 90])' in scad_content:
            logger.info("Using nested rotation (correct version)")
        elif 'rotate([90, 0, 90])' in scad_content:
            logger.info("Using single rotation (old version)")
        else:
            logger.warning("Rotation pattern not recognized")
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.scad', delete=False) as scad_file:
            scad_file.write(scad_content)
            scad_path = scad_file.name
        
        stl_path = scad_path.replace('.scad', '.stl')
        
        logger.info(f"SCAD file: {scad_path}")
        logger.info(f"STL file: {stl_path}")
        
        cmd = [
            'openscad',
            '-o', stl_path,
            '--export-format', 'binstl',
            scad_path
        ]
        
        logger.info(f"Running command: {' '.join(cmd)}")
        
        env = os.environ.copy()
        env['DISPLAY'] = ':99'
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            env=env
        )
        
        if result.returncode != 0:
            logger.error(f"OpenSCAD error: {result.stderr}")
            return jsonify({
                'error': 'OpenSCAD execution failed',
                'details': result.stderr
            }), 500
        
        if not os.path.exists(stl_path):
            logger.error("STL file not generated")
            return jsonify({
                'error': 'STL file not generated'
            }), 500
        
        logger.info(f"STL generated successfully: {stl_path}")
        
        response = send_file(
            stl_path,
            mimetype='application/octet-stream',
            as_attachment=True,
            download_name=f'{letter1}{letter2}_DUET.stl'
        )
        
        @response.call_on_close
        def cleanup():
            try:
                os.unlink(scad_path)
                os.unlink(stl_path)
                logger.info("Temporary files cleaned up")
            except Exception as e:
                logger.warning(f"Cleanup error: {e}")
        
        return response
        
    except Exception as e:
        logger.error(f"Error in generate_stl: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
