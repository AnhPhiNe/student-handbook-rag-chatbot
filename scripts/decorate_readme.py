import re

def decorate():
    with open('README.md', 'r', encoding='utf-8') as f:
        content = f.read()

    replacements = {
        "## Live Demo": "## 🚀 Live Demo",
        "## Key Features": "## ✨ Key Features",
        "## Architecture Overview": "## 🏗️ Architecture Overview",
        "## Supported Query Scope": "## 🎯 Supported Query Scope",
        "## Pipeline Overview": "## ⚙️ Pipeline Overview",
        "## Project Structure": "## 📁 Project Structure",
        "## Setup": "## 🛠️ Setup",
        "## Environment Variables": "## 🔐 Environment Variables",
        "## Run the Streamlit App": "## 💬 Run the Streamlit App",
        "## Run the FastAPI Backend": "## ⚡ Run the FastAPI Backend",
        "## Deployment Workflow": "## ☁️ Deployment Workflow",
        "## Local/API Manual Test": "## 🧪 Local/API Manual Test",
        "## Run Tests": "## ✅ Run Tests",
        "## Rebuild Local Data Artifacts": "## 🔄 Rebuild Local Data Artifacts",
        "## Retrieval Evaluation": "## 📊 Retrieval Evaluation",
        "## Example Questions": "## ❓ Example Questions",
        "## Demo Flow": "## 🎬 Demo Flow",
        "## Data Policy": "## ⚠️ Data Policy",
        "## License": "## 📄 License",
        "## Tech Stack": "## 💻 Tech Stack",
        "## Production Notes": "## 🏭 Production Notes",
        "## Limitations": "## 🚧 Limitations",
        "## Future Improvements": "## 🔮 Future Improvements",
    }
    
    for old, new in replacements.items():
        content = content.replace(old, new)
        
    # Wrap project structure in details
    struct_pattern = r"(## 📁 Project Structure\n\nCurrent production-oriented layout:\n\n```text\n.*?\n```\n)"
    content = re.sub(struct_pattern, 
        r"## 📁 Project Structure\n\n<details>\n<summary><b>Click to expand</b></summary>\n\nCurrent production-oriented layout:\n\n```text\n\g<0>".replace(r"\g<0>", "").replace("## 📁 Project Structure\n\nCurrent production-oriented layout:\n\n", "Current production-oriented layout:\n\n")[:-1] + "\n</details>\n",
        content, flags=re.DOTALL)
        
    # Add GitHub alerts
    content = content.replace("## ⚠️ Data Policy\n\nThis repository", "## ⚠️ Data Policy\n\n> [!IMPORTANT]\n> This repository")
    content = content.replace("## 🚧 Limitations\n\n- The answer quality", "## 🚧 Limitations\n\n> [!WARNING]\n> - The answer quality")
    content = content.replace("## 🏭 Production Notes\n\n- The system", "## 🏭 Production Notes\n\n> [!NOTE]\n> - The system")

    with open('README.md', 'w', encoding='utf-8') as f:
        f.write(content)
        
if __name__ == '__main__':
    decorate()
