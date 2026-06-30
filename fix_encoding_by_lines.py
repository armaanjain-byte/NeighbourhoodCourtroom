import os

def fix_transcript():
    with open('ui/components/transcript_view.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # We know the exact line numbers from our previous view_file/run_command
    # Lines are 0-indexed in python list
    lines[5] = "# ── Agent identity colours (exact hex, never approximate) ──────────────────\n"
    lines[25] = '    if agent_name == "finance": return "💰"\n'
    lines[26] = '    if agent_name == "climate": return "🌿"\n'
    lines[27] = '    return "🏘️"\n'
    
    # Line 49 in the file (index 48):
    lines[48] = "            ⚡ Responding to {escape(obj.target_agent.title())}'s claim that:\n"
    
    # Line 58 (index 57):
    lines[57] = "            ✓ Support → {sup.target_agent.title()}: {sup.reason}\n"
    
    # Line 65 (index 64):
    lines[64] = "            evidence_items += f'<li>{ev} <span style=\"display:inline;padding:1px 5px;background:#fefcbf;color:#744210;border:1px solid #744210;font-size:10px;font-weight:900;font-family:Outfit,sans-serif;text-transform:uppercase;\">⚠️ unverified</span></li>'\n"
    
    # Line 76 (index 75):
    lines[75] = "                🤝 Strategic Concession Rationale:\n"
    
    # Line 89 (index 88):
    lines[88] = "            ⚙️ Verified Baseline Calculation (AI reasoning unavailable)\n"
    
    # Line 97 (index 96):
    lines[96] = "        <!-- Phase label — Bauhaus square tag -->\n"
    
    # Line 102 (index 101):
    lines[101] = "            <div style=\"font-weight:900;font-family:Outfit,sans-serif;font-size:0.65rem;text-transform:uppercase;letter-spacing:0.08em;color:{accent};margin-bottom:3px;\">⚖ Weighing counter-consideration:</div>\n"
    
    # Line 110 (index 109):
    lines[109] = "                ▶ Evidence\n"

    with open('ui/components/transcript_view.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
if __name__ == '__main__':
    fix_transcript()
    print("Fixed via line indices!")
