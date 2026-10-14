from pathlib import Path
import re

reference=Path('/home/ubuntu/upload/pasted_content_10.txt').read_text()
section=re.search(r'## SEPTANEURON/about\.html\n\n```html\n(.*?)\n```',reference,re.S).group(1)
header=re.search(r'(<header class="sn-nav".*?</header>)',section,re.S).group(1)
footer=re.search(r'(<footer class="sn-footer".*?</footer>)',section,re.S).group(1)

def convert(s):
    replacements={
        'href="#"': 'href="{{ url_for(\'home\') }}"',
        'href="services.html"': 'href="{{ url_for(\'services\') }}"',
        'href="portfolio.html"': 'href="{{ url_for(\'portfolio\') }}"',
        'href="about.html"': 'href="{{ url_for(\'about\') }}"',
        'href="contact.html"': 'href="{{ url_for(\'contact\') }}"',
        'href="index.html"': 'href="{{ url_for(\'home\') }}"',
        'src="images/svgLogo/septaneuron.svg"': 'src="{{ url_for(\'static\', filename=\'assets/imgs/svgLogo/septaneuron.svg\') }}"',
    }
    for old,new in replacements.items():
        s=s.replace(old,new)
    return s

root=Path(__file__).parent/'templates'
(root/'navbar.html').write_text(convert(header)+'\n')
(root/'footer.html').write_text(convert(footer)+'\n')
print('navbar chars',len(header),'footer chars',len(footer))
