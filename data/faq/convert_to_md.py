# -*- coding: utf-8 -*-
import json, sys, os
sys.stdout.reconfigure(encoding='utf-8')

src = os.path.join(os.path.dirname(__file__), 'acme_collab_faq.json')
dst = os.path.join(os.path.dirname(__file__), 'acme_collab_faq.md')

with open(src, encoding='utf-8') as f:
    faqs = json.load(f)

lines = ['# Acme Collab FAQ Knowledge Base\n']
for faq in faqs:
    lines.append(f"## {faq['id']} — {faq['question']}")
    lines.append(f"\n**Category:** {faq['category']}")
    lines.append(f"\n**Answer:** {faq['answer']}\n")

with open(dst, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f"Done: {len(faqs)} FAQs → {dst}")
