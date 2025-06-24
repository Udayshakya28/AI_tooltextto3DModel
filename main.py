import os
from openfabric_pysdk.context import OpenfabricExecutionRay
from openfabric_pysdk.starter import Starter
from openfabric_pysdk.loader import ConfigClass, InputClass, OutputClass

import asyncio
from concurrent.futures import ThreadPoolExecutor

import logging
import json
import sqlite3
import os
from datetime import datetime
from typing import Dict, Optional
import requests
import base64

# Import the ontology classes (make sure these exist in your project)
from ontology_dc8f06af066e4a7880a5938933236037.config import ConfigClass
from ontology_dc8f06af066e4a7880a5938933236037.input import InputClass
from ontology_dc8f06af066e4a7880a5938933236037.output import OutputClass
from openfabric_pysdk.context import AppModel, State
from core.stub import Stub

# Configure logging
logging.basicConfig(level=logging.INFO)

# Configurations for the app
configurations: Dict[str, ConfigClass] = dict()

class MemoryManager:
    """Handles short-term and long-term memory for the AI system"""
    
    def __init__(self, db_path: str = "ai_memory.db"):
        self.db_path = db_path
        self.session_memory = {}  # Short-term memory
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database for long-term memory"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                user_prompt TEXT,
                enhanced_prompt TEXT,
                image_path TEXT,
                model_3d_path TEXT,
                tags TEXT
            )
        ''')
        conn.commit()
        conn.close()
    
    def save_generation(self, user_prompt: str, enhanced_prompt: str, 
                       image_path: str = None, model_3d_path: str = None, tags: str = None):
        """Save a generation to long-term memory"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO generations (timestamp, user_prompt, enhanced_prompt, image_path, model_3d_path, tags)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (datetime.now().isoformat(), user_prompt, enhanced_prompt, image_path, model_3d_path, tags))
        conn.commit()
        conn.close()
    
    def search_memory(self, query: str, limit: int = 5):
        """Search long-term memory for similar prompts"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM generations 
            WHERE user_prompt LIKE ? OR enhanced_prompt LIKE ? OR tags LIKE ?
            ORDER BY timestamp DESC LIMIT ?
        ''', (f'%{query}%', f'%{query}%', f'%{query}%', limit))
        results = cursor.fetchall()
        conn.close()
        return results

class LocalLLMHandler:
    """Handles communication with local LLM (DeepSeek/Llama via Ollama)"""
    
    def __init__(self, model_name: str = "deepseek-r1:1.5b", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url
    
    def enhance_prompt(self, user_prompt: str, memory_context: str = "") -> str:
        """Use LLM to enhance and expand the user's prompt"""
        system_prompt = """You are a creative AI assistant that enhances image generation prompts. 
        Take the user's simple request and expand it into a detailed, vivid description that would 
        produce stunning visual results. Focus on:
        - Visual details (lighting, composition, colors, textures)
        - Artistic style and mood
        - Technical photography/art terms
        - Environmental context
        
        Keep the core idea but make it more descriptive and artistic."""
        
        if memory_context:
            system_prompt += f"\n\nContext from previous interactions: {memory_context}"
        
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": f"System: {system_prompt}\n\nUser request: {user_prompt}\n\nEnhanced prompt:",
                    "stream": False
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('response', user_prompt).strip()
            else:
                logging.warning(f"LLM request failed: {response.status_code}")
                return user_prompt
                
        except Exception as e:
            logging.error(f"Error communicating with LLM: {e}")
            return user_prompt

class CreativePipeline:
    """Main pipeline orchestrating the creative process"""
    
    def __init__(self, stub: Stub, memory_manager: MemoryManager, llm_handler: LocalLLMHandler):
        self.stub = stub
        self.memory = memory_manager
        self.llm = llm_handler
        self.text_to_image_app = 'f0997a01-d6d3-a5fe-53d8-561300318557'
        self.image_to_3d_app = '69543f29-4d41-4afc-7f29-3d51591f11eb'
    
    def process_request(self, user_prompt: str, user_id: str = 'super-user') -> Dict:
        """Main processing pipeline"""
        results = {
            'user_prompt': user_prompt,
            'enhanced_prompt': '',
            'image_generated': False,
            'model_3d_generated': False,
            'image_path': None,
            'model_path': None,
            'error': None
        }
        
        try:
            # Step 1: Search memory for context
            memory_results = self.memory.search_memory(user_prompt, limit=3)
            memory_context = ""
            if memory_results:
                memory_context = f"Similar past requests: {[r[2] for r in memory_results[:2]]}"
            
            # Step 2: Enhance prompt with LLM
            logging.info(f"Enhancing prompt: {user_prompt}")
            enhanced_prompt = self.llm.enhance_prompt(user_prompt, memory_context)
            results['enhanced_prompt'] = enhanced_prompt
            
            # Step 3: Generate image
            logging.info(f"Generating image with prompt: {enhanced_prompt}")
            image_result = self.generate_image(enhanced_prompt, user_id)
            
            if image_result['success']:
                results['image_generated'] = True
                results['image_path'] = image_result['path']
                
                # Step 4: Generate 3D model from image
                logging.info("Converting image to 3D model")
                model_result = self.generate_3d_model(image_result['data'], user_id)
                
                if model_result['success']:
                    results['model_3d_generated'] = True
                    results['model_path'] = model_result['path']
                else:
                    results['error'] = model_result.get('error', 'Failed to generate 3D model')
            else:
                results['error'] = image_result.get('error', 'Failed to generate image')
            
            # Step 5: Save to memory
            self.memory.save_generation(
                user_prompt=user_prompt,
                enhanced_prompt=enhanced_prompt,
                image_path=results['image_path'],
                model_3d_path=results['model_path'],
                tags=self.extract_tags(enhanced_prompt)
            )
            
        except Exception as e:
            logging.error(f"Pipeline error: {e}")
            results['error'] = str(e)
        
        return results
    
    def generate_image(self, prompt: str, user_id: str) -> Dict:
        """Generate image using Openfabric text-to-image app"""
        try:
            # Call the Text to Image app
            response = self.stub.call(
                f'{self.text_to_image_app}.node3.openfabric.network',
                {'prompt': prompt},
                user_id
            )
            
            image_data = response.get('result')
            if image_data:
                # Save image to file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                image_path = f'outputs/image_{timestamp}.png'
                os.makedirs('outputs', exist_ok=True)
                
                # Handle different data types
                if isinstance(image_data, str):
                    # If it's base64 encoded
                    try:
                        image_bytes = base64.b64decode(image_data)
                    except:
                        image_bytes = image_data.encode()
                else:
                    image_bytes = image_data
                
                with open(image_path, 'wb') as f:
                    f.write(image_bytes)
                
                return {'success': True, 'path': image_path, 'data': image_bytes}
            else:
                return {'success': False, 'error': 'No image data received'}
                
        except Exception as e:
            logging.error(f"Image generation error: {e}")
            return {'success': False, 'error': str(e)}
    
    def generate_3d_model(self, image_data: bytes, user_id: str) -> Dict:
        """Generate 3D model using Openfabric image-to-3D app"""
        try:
            # Convert image data to base64 for the 3D app
            image_b64 = base64.b64encode(image_data).decode('utf-8')
            
            response = self.stub.call(
                f'{self.image_to_3d_app}.node3.openfabric.network',
                {'image': image_b64},
                user_id
            )
            
            model_data = response.get('result')
            if model_data:
                # Save 3D model to file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                model_path = f'outputs/model_{timestamp}.obj'
                
                # Handle different data types
                if isinstance(model_data, str):
                    try:
                        model_bytes = base64.b64decode(model_data)
                    except:
                        model_bytes = model_data.encode()
                else:
                    model_bytes = model_data
                
                with open(model_path, 'wb') as f:
                    f.write(model_bytes)
                
                return {'success': True, 'path': model_path, 'data': model_bytes}
            else:
                return {'success': False, 'error': 'No 3D model data received'}
                
        except Exception as e:
            logging.error(f"3D model generation error: {e}")
            return {'success': False, 'error': str(e)}
    
    def extract_tags(self, prompt: str) -> str:
        """Extract relevant tags from enhanced prompt for memory search"""
        # Simple keyword extraction - could be enhanced with NLP
        import re
        words = re.findall(r'\b\w+\b', prompt.lower())
        # Filter out common words and keep meaningful ones
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        tags = [word for word in words if len(word) > 3 and word not in stop_words]
        return ','.join(tags[:10])  # Keep top 10 tags

# Global instances
memory_manager = MemoryManager()
llm_handler = LocalLLMHandler()

############################################################
# Config callback function
############################################################
def config(configuration: Dict[str, ConfigClass], state: State) -> None:
    """
    Stores user-specific configuration data.

    Args:
        configuration (Dict[str, ConfigClass]): A mapping of user IDs to configuration objects.
        state (State): The current state of the application (not used in this implementation).
    """
    for uid, conf in configuration.items():
        logging.info(f"Saving new config for user with id:'{uid}'")
        configurations[uid] = conf

############################################################
# Execution callback function
############################################################
def execute(model: AppModel) -> None:
    """
    Main execution entry point for handling a model pass.

    Args:
        model (AppModel): The model object containing request and response structures.
    """
    request: InputClass = model.request

    # Retrieve user config
    user_config: ConfigClass = configurations.get('super-user', None)
    logging.info(f"User config: {configurations}")

    if not os.getenv('OPENFABRIC_API_KEY'):
        print("Warning: No OPENFABRIC_API_KEY found in environment")
    
    # Initialize the Stub with app IDs
    app_ids = user_config.app_ids if user_config else []
    stub = Stub(app_ids)
    
    # Test the apps are reachable before using them
    test_apps_connectivity(stub)

    # Initialize the creative pipeline
    pipeline = CreativePipeline(stub, memory_manager, llm_handler)
    
    # Process the user's request
    results = pipeline.process_request(request.prompt)
    
    # Prepare detailed response
    response: OutputClass = model.response
    
    if results['error']:
        response.message = f"Error processing request: {results['error']}"
    else:
        status_parts = []
        status_parts.append(f"Original prompt: {results['user_prompt']}")
        status_parts.append(f"Enhanced prompt: {results['enhanced_prompt']}")
        
        if results['image_generated']:
            status_parts.append(f"✅ Image generated: {results['image_path']}")
        else:
            status_parts.append("❌ Image generation failed")
            
        if results['model_3d_generated']:
            status_parts.append(f"✅ 3D model generated: {results['model_path']}")
        else:
            status_parts.append("❌ 3D model generation failed")
        
        response.message = "\n".join(status_parts)
    
    logging.info(f"Pipeline execution completed: {results}")

def test_apps_connectivity(stub):
    """Test if apps are reachable"""
    apps = [
        'f0997a01-d6d3-a5fe-53d8-561300318557',  # Text to Image
        '69543f29-4d41-4afc-7f29-3d51591f11eb'   # Image to 3D
    ]
    
    for app_id in apps:
        try:
            # Try to ping the app
            response = requests.get(f"https://{app_id}.node3.openfabric.network/health", timeout=10)
            print(f"App {app_id}: {'✅' if response.status_code == 200 else '❌'}")
        except Exception as e:
            print(f"App {app_id}: ❌ {e}")

# Add the missing ignite code
if __name__ == '__main__':
    PORT = 8888
    Starter.ignite(debug=False, host="0.0.0.0", port=PORT)