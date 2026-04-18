import glob

def clean():
    files = glob.glob(r'c:\Users\Narsing\Desktop\unicred\templates\**\*.html', recursive=True)
    count = 0
    
    # Match EXACT explicit string including the \ character
    t_hidden = r"type=\'hidden\'"
    n_csrf = r"name=\'csrf_token\'"
    v_csrf = r"value=\'{{ csrf_token() }}\'"
    
    for f in files:
        with open(f, 'r', encoding='utf-8') as file:
            c = file.read()
            
        orig = c
        c = c.replace(t_hidden, 'type="hidden"')
        c = c.replace(n_csrf, 'name="csrf_token"')
        c = c.replace(v_csrf, 'value="{{ csrf_token() }}"')
        
        if c != orig:
            with open(f, 'w', encoding='utf-8') as file:
                file.write(c)
            count += 1
            print(f"Fixed {f}")
            
    print(f"Total files fixed: {count}")

if __name__ == '__main__':
    clean()
