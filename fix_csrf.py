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
            return True
        else:
            print(f"No CSRF token to fix in {file_path}")
            return False
    except Exception as e:
        print(f"Error processing {file_path}: {str(e)}")
        return False

def remove_csrf_token(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Check if the file contains CSRF token input
        if '<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">' in content:
            # Remove CSRF token input
            content = content.replace('<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">', '')
            
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(content)
            
            print(f"Removed CSRF token from {file_path}")
            return True
        else:
            print(f"No CSRF token to remove in {file_path}")
            return False
    except Exception as e:
        print(f"Error processing {file_path}: {str(e)}")
        return False

def main():
    # Fix all templates
    template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    print(f"Scanning templates in {template_dir}")
    
    if not os.path.exists(template_dir):
        print(f"Template directory not found: {template_dir}")
        return
    
    fixed_count = 0
    for filename in os.listdir(template_dir):
        if filename.endswith('.html'):
            file_path = os.path.join(template_dir, filename)
            if fix_template(file_path):
                fixed_count += 1
    
    print(f"Fixed {fixed_count} templates")
    
    # Remove CSRF tokens from all templates
    removed_count = 0
    for filename in os.listdir(template_dir):
        if filename.endswith('.html'):
            file_path = os.path.join(template_dir, filename)
            if remove_csrf_token(file_path):
                removed_count += 1
    
    print(f"Removed CSRF tokens from {removed_count} templates")
    
    # Also check for Git merge conflict markers
    print("\nChecking for Git merge conflict markers...")
    conflict_count = 0
    for filename in os.listdir(template_dir):
        if filename.endswith('.html'):
            file_path = os.path.join(template_dir, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    content = file.read()
                
                if '<<<<<<< ' in content or '=======' in content or '>>>>>>> ' in content:
                    print(f"Found Git merge conflicts in {file_path}")
                    conflict_count += 1
            except Exception as e:
                print(f"Error checking for conflicts in {file_path}: {str(e)}")
    
    print(f"Found {conflict_count} files with Git merge conflicts")

if __name__ == "__main__":
    main()