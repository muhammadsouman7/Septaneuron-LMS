from pathlib import Path
import re

source=Path('/home/ubuntu/upload/pasted_content_10.txt').read_text()
out=Path(__file__).parent/'static'/'assets'/'css'
for name in ['navbar.css','hero.css','footer.css','footer-responsive.css','about.css','contact.css','portfolio.css','services.css','services-additions.css','services-interactions.css']:
    pattern=rf'## SEPTANEURON/css/{re.escape(name)}\n\n```css\n(.*?)\n```'
    match=re.search(pattern,source,re.S)
    if match:
        (out/name).write_text(match.group(1)+'\n')
        print('restored',name,len(match.group(1)))
    else:
        print('missing',name)
