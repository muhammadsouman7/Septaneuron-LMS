from pathlib import Path
import json,re
root=Path(__file__).parent
page_dir=Path('/home/ubuntu/SEPTANEURON/react-app/src/pageData')

def route_link(match):
    href=match.group(1)
    mapping={'index':'home','about':'about','contact':'contact','portfolio':'portfolio','services':'services'}
    if href.startswith('#') or href.startswith('mailto:'):
        return f'href="{href}"'
    base=href.split('#')[0].replace('.html','')
    if base in mapping:
        anchor=('#'+href.split('#',1)[1]) if '#' in href else ''
        return f'href="{{{{ url_for(\'{mapping[base]}\') }}}}{anchor}"'
    return f'href="{href}"'

for name in ['about','contact','portfolio','services']:
    data=json.loads((page_dir/f'{name}.json').read_text())
    source=data['body']
    ambient=source.split('<header',1)[0]
    main=re.search(r'<main>(.*?)</main>', source, re.S|re.I)
    body=main.group(1) if main else source
    body=re.sub(r'href="([^"]+)"', route_link, body)
    page=f'''{{% extends "base.html" %}}\n{{% block title %}}{data['title']}{{% endblock %}}\n{{% block page_css %}}<link rel="stylesheet" href="{{{{ url_for('static', filename='assets/css/{name}.css') }}}}">{{% endblock %}}\n{{% block content %}}\n{ambient}{body}\n{{% endblock %}}\n{{% block page_scripts %}}<script src="{{{{ url_for('static', filename='assets/js/{name}.js') }}}}"></script>{{% endblock %}}\n'''
    (root/'templates'/f'{name}.html').write_text(page)
