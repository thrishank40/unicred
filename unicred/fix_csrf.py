import os, glob

def fix_csrf_escaping():
    target_files = glob.glob(r'c:\Users\Narsing\Desktop\unicred\templates\**\*.html', recursive=True)
    for filepath in target_files:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Replace the broken escaped values with proper quotes
        broken_tags = [
            "type=\\'hidden\\'",
            "name=\\'csrf_token\\'",
            "value=\\'{{ csrf_token() }}\\'"
        ]
        
        if any(broken in content for broken in broken_tags):
            content = content.replace("type=\\'hidden\\'", 'type="hidden"')
            content = content.replace("name=\\'csrf_token\\'", 'name="csrf_token"')
            content = content.replace("value=\\'{{ csrf_token() }}\\'", 'value="{{ csrf_token() }}"')
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Fixed: {filepath}")

if __name__ == "__main__":
    fix_csrf_escaping()
