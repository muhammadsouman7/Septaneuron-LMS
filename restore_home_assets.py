from pathlib import Path
import re

ref=Path('/home/ubuntu/upload/pasted_content_10.txt').read_text()
root=Path(__file__).parent
cssout=root/'static/assets/css'; jsout=root/'static/assets/js'; templates=root/'templates'
for name in ['homepage-sections.css']:
    m=re.search(rf'## SEPTANEURON/css/{re.escape(name)}\n\n```css\n(.*?)\n```',ref,re.S)
    if m:(cssout/name).write_text(m.group(1)+'\n')
for name in ['about.js','contact.js','footer.js','hero.js','homepage-sections.js','navbar.js','portfolio.js','services.js']:
    m=re.search(rf'## SEPTANEURON/js/{re.escape(name)}\n\n```javascript\n(.*?)\n```',ref,re.S)
    if not m:m=re.search(rf'## SEPTANEURON/js/{re.escape(name)}\n\n```js\n(.*?)\n```',ref,re.S)
    if m:(jsout/name).write_text(m.group(1)+'\n')

m=re.search(r'## SEPTANEURON/index\.html\n\n```html\n(.*?)\n```',ref,re.S)
html=m.group(1)
body=re.search(r'<body>(.*?)</body>',html,re.S|re.I).group(1)
header=re.search(r'<header class="sn-nav".*?</header>',body,re.S).group(0)
footer=re.search(r'<footer class="sn-footer".*?</footer>',body,re.S).group(0)
main_start=body.index('<main class="sn-home-sections">')
hero_start=body.index('<div class="hero"')
hero=body[hero_start:main_start]
main=re.search(r'<main class="sn-home-sections">(.*?)</main>',body,re.S).group(1)
ambient=body[:hero_start]
ambient=re.sub(r'<header class="sn-nav".*?</header>', '', ambient, flags=re.S)
def links(s):
    return s.replace('href="#"','href="{{ url_for(\'home\') }}"').replace('href="services.html"','href="{{ url_for(\'services\') }}"').replace('href="portfolio.html"','href="{{ url_for(\'portfolio\') }}"').replace('href="about.html"','href="{{ url_for(\'about\') }}"').replace('href="contact.html"','href="{{ url_for(\'contact\') }}"').replace('src="images/','src="{{ url_for(\'static\', filename=\'assets/imgs/')
footer=links(footer).replace('septaneuron.svg"','septaneuron.svg\' ) }}"')
header=links(header)
page=f'''{{% extends "base.html" %}}\n{{% block title %}}Septaneuron{{% endblock %}}\n{{% block page_css %}}<link rel="stylesheet" href="{{{{ url_for('static', filename='assets/css/homepage-sections.css') }}}}">{{% endblock %}}\n{{% block content %}}\n{ambient}\n{hero}\n<main class="sn-home-sections">{main}</main>\n{{% endblock %}}\n{{% block page_scripts %}}<script src="{{{{ url_for('static', filename='assets/js/homepage-sections.js') }}}}"></script>{{% endblock %}}\n'''
(templates/'home.html').write_text(page)
