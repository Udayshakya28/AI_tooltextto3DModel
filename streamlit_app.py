import streamlit as st
import requests
import json
import os
from datetime import datetime
import sqlite3
from PIL import Image
import base64
import time
import logging

# Configure logging to show errors in the console
logging.basicConfig(level=logging.ERROR, format='%(asctime)s %(levelname)s %(message)s')


# Configure page
st.set_page_config(
    page_title="AI Creative Pipeline",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        background: linear-gradient(90deg, #ff6b6b, #4ecdc4);
        background-clip: text;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 2rem;
    }
    
    .pipeline-step {
        background: #f0f2f6;
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
        border-left: 4px solid #4ecdc4;
    }
    
    .success-box {
        background: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 5px;
        padding: 1rem;
        margin: 1rem 0;
    }
    
    .error-box {
        background: #f8d7da;
        border: 1px solid #f5c6cb;
        border-radius: 5px;
        padding: 1rem;
        margin: 1rem 0;
    }
    
    .memory-card {
        background: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)
class StreamlitMemoryManager:
    """Memory manager for Streamlit interface"""

    def __init__(self, db_path: str = "ai_memory.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize database if it doesn't exist"""
        if not os.path.exists(self.db_path):
            try:
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
            except Exception as e:
                print(f"Database init error: {e}")
                logging.error(f"Database init error: {e}")
                st.error(f"Database init error: {e}")

    def get_recent_generations(self, limit: int = 10):
        """Get recent generations from memory"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM generations 
                ORDER BY timestamp DESC LIMIT ?
            ''', (limit,))
            results = cursor.fetchall()
            conn.close()
            return results
        except Exception as e:
            print(f"Database error: {e}")
            logging.error(f"Database error: {e}")
            st.error(f"Database error: {e}")
            return []

    def search_generations(self, query: str, limit: int = 5):
        """Search generations by query"""
        try:
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
        except Exception as e:
            print(f"Search error: {e}")
            logging.error(f"Search error: {e}")
            st.error(f"Search error: {e}")
            return []

def call_pipeline_api(prompt: str):
    """Call the main pipeline API with correct endpoint"""
    try:
        response = requests.post(
            "http://localhost:8888/execution",
            json={
                "prompt": prompt
            },
            headers={"Content-Type": "application/json"},
            timeout=120
        )
        if response.status_code == 200:
            return {"success": True, "data": response.json()}
        else:
            error_msg = f"API call failed: {response.status_code} - {response.text}"
            print(error_msg)
            logging.error(error_msg)
            return {"success": False, "error": error_msg}
    except requests.exceptions.RequestException as e:
        print(f"Connection error: {e}")
        logging.error(f"Connection error: {e}")
        return {"success": False, "error": f"Connection error: {str(e)}"}


def check_service_status(url: str, timeout: int = 5) -> bool:
    """Check if a service is running"""
    try:
        response = requests.get(url, timeout=timeout)
        return response.status_code == 200
    except:
        return False

def parse_pipeline_response(message: str):
    """Parse the pipeline response message"""
    lines = message.split('\n')
    
    parsed_data = {
        'original_prompt': '',
        'enhanced_prompt': '',
        'image_status': '',
        'model_status': '',
        'image_path': None,
        'model_path': None
    }
    
    for line in lines:
        line = line.strip()
        if line.startswith("Original prompt:"):
            parsed_data['original_prompt'] = line.replace("Original prompt: ", "")
        elif line.startswith("Enhanced prompt:"):
            parsed_data['enhanced_prompt'] = line.replace("Enhanced prompt: ", "")
        elif "Image generated:" in line:
            parsed_data['image_status'] = line
            # Extract path
            if "Image generated:" in line:
                parsed_data['image_path'] = line.split("Image generated: ")[1].strip()
        elif "Image generation failed" in line:
            parsed_data['image_status'] = line
        elif "3D model generated:" in line:
            parsed_data['model_status'] = line
            # Extract path
            if "3D model generated:" in line:
                parsed_data['model_path'] = line.split("3D model generated: ")[1].strip()
        elif "3D model generation failed" in line:
            parsed_data['model_status'] = line
    
    return parsed_data

def display_generation_results(response_data):
    """Display the results of the generation"""
    message = response_data.get("message", "")
    parsed = parse_pipeline_response(message)
    
    # Success message
    st.markdown('<div class="success-box">', unsafe_allow_html=True)
    st.success("🎉 Generation pipeline completed!")
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Show pipeline steps
    st.subheader("🔄 Pipeline Steps")
    
    steps = [
        ("🎯 Original Prompt", parsed['original_prompt']),
        ("✨ Enhanced Prompt", parsed['enhanced_prompt'][:200] + "..." if len(parsed['enhanced_prompt']) > 200 else parsed['enhanced_prompt']),
        ("🖼️ Image Generation", parsed['image_status'] or "Processing..."),
        ("🎨 3D Model Generation", parsed['model_status'] or "Processing...")
    ]
    
    for step_name, step_content in steps:
        if step_content:
            st.markdown(f'<div class="pipeline-step"><strong>{step_name}:</strong> {step_content}</div>', unsafe_allow_html=True)
    
    # Display generated files
    col1, col2 = st.columns(2)
    
    with col1:
        if parsed['image_path'] and os.path.exists(parsed['image_path']):
            st.subheader("🖼️ Generated Image")
            try:
                image = Image.open(parsed['image_path'])
                st.image(image, caption="AI Generated Image", use_column_width=True)
                
                # Download button for image
                with open(parsed['image_path'], "rb") as file:
                    st.download_button(
                        label="📥 Download Image",
                        data=file.read(),
                        file_name=os.path.basename(parsed['image_path']),
                        mime="image/png"
                    )
            except Exception as e:
                st.error(f"Could not display image: {e}")
        elif "Image generation failed" in message:
            st.error("❌ Image generation failed")
        else:
            st.info("🔄 Image generation in progress...")
    
    with col2:
        if parsed['model_path'] and os.path.exists(parsed['model_path']):
            st.subheader("🎯 3D Model")
            st.success(f"3D model generated successfully!")
            st.info(f"Model saved to: {os.path.basename(parsed['model_path'])}")
            
            # Download button for 3D model
            try:
                with open(parsed['model_path'], "rb") as file:
                    st.download_button(
                        label="📥 Download 3D Model",
                        data=file.read(),
                        file_name=os.path.basename(parsed['model_path']),
                        mime="application/octet-stream"
                    )
            except Exception as e:
                st.error(f"Could not prepare download: {e}")
        elif "3D model generation failed" in message:
            st.error("❌ 3D model generation failed")
        else:
            st.info("🔄 3D model generation in progress...")

def display_memory_item(generation):
    """Display a single memory item"""
    id_val, timestamp, user_prompt, enhanced_prompt, image_path, model_path, tags = generation
    
    # Format timestamp
    try:
        dt = datetime.fromisoformat(timestamp)
        formatted_time = dt.strftime("%Y-%m-%d %H:%M")
    except:
        formatted_time = timestamp
    
    with st.expander(f"🎨 {user_prompt[:50]}..." if len(user_prompt) > 50 else user_prompt):
        st.markdown(f"**📅 Created:** {formatted_time}")
        st.markdown(f"**🎯 Original Prompt:** {user_prompt}")
        
        if enhanced_prompt:
            st.markdown(f"**✨ Enhanced Prompt:** {enhanced_prompt[:150]}..." if len(enhanced_prompt) > 150 else enhanced_prompt)
        
        if tags:
            st.markdown(f"**🏷️ Tags:** {tags}")
        
        # Show generated files if they exist
        file_col1, file_col2 = st.columns(2)
        
        with file_col1:
            if image_path and os.path.exists(image_path):
                try:
                    image = Image.open(image_path)
                    st.image(image, caption="Generated Image", width=200)
                except Exception as e:
                    st.write(f"Image: {os.path.basename(image_path)} (cannot display)")
            
        with file_col2:
            if model_path and os.path.exists(model_path):
                st.write(f"**3D Model:** {os.path.basename(model_path)}")
                try:
                    with open(model_path, "rb") as file:
                        st.download_button(
                            label="📥 Download",
                            data=file.read(),
                            file_name=os.path.basename(model_path),
                            mime="application/octet-stream",
                            key=f"download_{id_val}"
                        )
                except:
                    st.write("Download unavailable")

def show_system_status():
    """Show comprehensive system status"""
    st.subheader("🔧 System Status")
    
    # Check backend services
    services = [
        ("Main Pipeline API", "http://localhost:8888/manifest", "🚀"),
        ("Local LLM (Ollama)", "http://localhost:11434/api/tags", "🧠"),
    ]
    
    for name, url, icon in services:
        status = "🟢 Online" if check_service_status(url) else "🔴 Offline"
        st.write(f"{icon} **{name}:** {status}")
    
    # Check directories and files
    st.write("\n**📁 File System:**")
    checks = [
        ("Outputs Directory", os.path.exists('outputs')),
        ("Memory Database", os.path.exists('ai_memory.db')),
        ("Environment File", os.path.exists('.env')),
    ]
    
    for name, exists in checks:
        status = "✅" if exists else "❌"
        st.write(f"{status} {name}")
    
    # Environment variables
    env_vars = ["OPENFABRIC_API_KEY"]
    st.write("\n**🔑 Environment Variables:**")
    for var in env_vars:
        status = "✅ Set" if os.getenv(var) else "❌ Missing"
        st.write(f"{status} {var}")

def main():
    # Header
    st.markdown('<h1 class="main-header">🚀 AI Creative Pipeline</h1>', unsafe_allow_html=True)
    st.markdown("### Transform your ideas into stunning 3D models with AI magic!")
    
    # Initialize memory manager
    memory_manager = StreamlitMemoryManager()
    
    # Sidebar
    with st.sidebar:
        st.header("🎨 Creative Tools")
        
        # Pipeline status
        st.subheader("Pipeline Status")
        
        # Check if services are running
        api_status = "🟢 Online" if check_service_status("http://localhost:8888/manifest") else "🔴 Offline"
        ollama_status = "🟢 Online" if check_service_status("http://localhost:11434/api/tags") else "🔴 Offline"
        
        st.write(f"**Main API:** {api_status}")
        st.write(f"**Local LLM:** {ollama_status}")
        
        # Memory stats
        recent_gens = memory_manager.get_recent_generations(100)
        st.write(f"**Total Generations:** {len(recent_gens)}")
        
        st.divider()
        
        # Quick examples
        st.subheader("💡 Quick Examples")
        example_prompts = [
            "Glowing dragon on a cliff at sunset",
            "Cyberpunk city skyline at night",
            "Magical forest with floating crystals",
            "Steampunk robot with brass gears",
            "Ethereal jellyfish in deep space"
        ]
        
        for prompt in example_prompts:
            if st.button(prompt, key=f"example_{prompt}"):
                st.session_state.prompt_input = prompt
        
        st.divider()
        
        # System status section
        with st.expander("🔧 System Status"):
            show_system_status()
            
            if st.button("Test API Connection"):
                try:
                    response = requests.get("http://localhost:8888/manifest", timeout=5)
                    st.success(f"✅ API Response: {response.status_code}")
                    if response.status_code == 200:
                        try:
                            st.json(response.json())
                        except:
                            st.text(response.text)
                except Exception as e:
                    st.error(f"❌ API Error: {e}")
    
    # Main content area
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("✨ Create Something Amazing")
        
        # Input form
        with st.form("creative_form"):
            prompt_input = st.text_area(
                "Describe your vision:",
                value=st.session_state.get('prompt_input', ''),
                height=100,
                placeholder="e.g., A majestic phoenix rising from flames with golden feathers, cinematic lighting, 4K resolution..."
            )
            
            col_submit, col_clear = st.columns([1, 1])
            with col_submit:
                submit_button = st.form_submit_button("🚀 Generate", use_container_width=True)
            with col_clear:
                clear_button = st.form_submit_button("🗑️ Clear", use_container_width=True)
        
        if clear_button:
            st.session_state.prompt_input = ""
            st.rerun()
        
        # Process generation
        if submit_button and prompt_input:
            # Check API status first
            if not check_service_status("http://localhost:8888/manifest"):
                st.error("❌ Backend API is not running. Please start the OpenFabric backend first.")
                st.info("**To start the backend:**\n1. Run: `python main.py`\n2. Make sure Ollama is running: `ollama serve`\n3. Ensure DeepSeek model is installed: `ollama pull deepseek-r1:1.5b`")
                return
            
            with st.spinner("🔮 AI is working its magic..."):
                # Progress indicators
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                status_text.text("🧠 Enhancing prompt with AI...")
                progress_bar.progress(20)
                
                # Call the pipeline
                result = call_pipeline_api(prompt_input)
                
                if result["success"]:
                    progress_bar.progress(50)
                    status_text.text("🎨 Generating image...")
                    
                    # Simulate progress updates
                    time.sleep(1)
                    progress_bar.progress(75)
                    status_text.text("🔄 Converting to 3D model...")
                    
                    time.sleep(1)
                    progress_bar.progress(100)
                    status_text.text("✅ Generation complete!")
                    
                    # Display results
                    display_generation_results(result["data"])
                
                else:
                    progress_bar.progress(0)
                    status_text.text("")
                    st.markdown('<div class="error-box">', unsafe_allow_html=True)
                    st.error(f"❌ Generation failed: {result['error']}")
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Show troubleshooting tips
                    st.subheader("🔧 Troubleshooting")
                    st.info("""
                    **Common issues and solutions:**
                    
                    1. **Backend not running**
                       - Start with: `python main.py`
                    
                    2. **Ollama not running**
                       - Start with: `ollama serve`
                    
                    3. **Required model not installed**
                       - Run: `ollama pull deepseek-r1:1.5b`
                    
                    4. **OpenFabric API key missing**
                       - Set environment variable: `OPENFABRIC_API_KEY=your_key`
                    
                    5. **Network connectivity issues**
                       - Check internet connection
                       - Verify OpenFabric service availability
                    """)
    
    with col2:
        st.subheader("📚 Memory & History")
        
        # Search functionality
        search_query = st.text_input("🔍 Search past generations:", placeholder="dragon, cyberpunk, etc.")
        
        # Filter options
        with st.expander("⚙️ Filter Options"):
            show_limit = st.slider("Number of results", 5, 50, 10)
            date_filter = st.selectbox("Time period", ["All time", "Last day", "Last week", "Last month"])
        
        if search_query:
            search_results = memory_manager.search_generations(search_query, show_limit)
        else:
            search_results = memory_manager.get_recent_generations(show_limit)
        
        if search_results:
            st.write(f"**Found {len(search_results)} generation(s):**")
            
            for generation in search_results:
                display_memory_item(generation)
        else:
            st.info("🎨 No generations found. Create your first masterpiece!")
            
        # Memory management
        with st.expander("🗄️ Memory Management"):
            st.write(f"**Database:** {memory_manager.db_path}")
            st.write(f"**Total Records:** {len(memory_manager.get_recent_generations(1000))}")
            
            if st.button("🗑️ Clear All Memory", type="secondary"):
                if st.checkbox("I understand this will delete all saved generations"):
                    try:
                        conn = sqlite3.connect(memory_manager.db_path)
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM generations")
                        conn.commit()
                        conn.close()
                        st.success("✅ Memory cleared successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error clearing memory: {e}")

if __name__ == "__main__":
    main()