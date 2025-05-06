import os

def fix_template(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Check if the file contains the pattern to replace
        if '{{ form.csrf_token }}' in content:
            # Replace form.csrf_token with direct input
            content = content.replace('{{ form.csrf_token }}', 
                                    '<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">')
            
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(content)
            
            print(f"Fixed CSRF token in {file_path}")
        else:
            print(f"No CSRF token to fix in {file_path}")
    except Exception as e:
        print(f"Error processing {file_path}: {str(e)}")

def main():
    # Fix all templates
    template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    print(f"Scanning templates in {template_dir}")
    
    if not os.path.exists(template_dir):
        print(f"Template directory not found: {template_dir}")
        return
    
    for filename in os.listdir(template_dir):
        if filename.endswith('.html'):
            file_path = os.path.join(template_dir, filename)
            fix_template(file_path)

if __name__ == "__main__":
    main()