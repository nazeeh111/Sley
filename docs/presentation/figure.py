"""Original constraint/drawdown schematic generated from the actual native plan."""
from pathlib import Path
import json,html
P=Path(__file__).resolve().parent
plan=json.loads((P/'feasible.json').read_text());check=json.loads((P/'reopen-check.json').read_text());assert check['freshNativeImportLiftplan']==[r['raised_shafts'] for r in plan['picks']];assert plan['declared_fixed_tie_up']==[[1],None,[]];assert plan['declared_allowed_pairs']==[[1,2]]
def draw(phone):
 W,H=(420,1290) if phone else (1200,900);out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="sley-title sley-desc"><title id="sley-title">Keep the lifts. Change the footwork.</title><desc id="sley-desc">An actual four-pick synthetic weaving draft uses three physical pedal positions. Pedal 1 is fixed to shaft 1, pedal 2 is assigned shaft 2, and pedal 3 stays untied. Picks press 1, then 2, then the allowed pair 1 and 2, then no pedal. All eight drawdown cells and original lifts survive WIF export and fresh reopening. Without pair 1 and 2 these fixed constraints are infeasible. This is a rising-shed union model, not physical loom validation.</desc><rect width="100%" height="100%" fill="#f7f5ef"/>']
 def t(x,y,s,size=18,color='#192533',bold=False,anchor=None):out.append(f'<text x="{x}" y="{y}" font-family="Arial,Helvetica,sans-serif" font-size="{size}" fill="{color}"'+(' font-weight="700"' if bold else '')+(f' text-anchor="{anchor}"' if anchor else '')+'>'+html.escape(str(s))+'</text>')
 def cell(kind,row,col,x,y,v,sz=42):out.append(f'<rect data-kind="{kind}" data-row="{row}" data-col="{col}" data-value="{int(v)}" x="{x}" y="{y}" width="{sz}" height="{sz}" fill="{("#263f55" if v else "#fffdf7")}" stroke="#9ca9b1"/>')
 t(26,36,'SLEY / ONE DRAFT, FIXED PHYSICAL PEDALS',12,'#185fbd',True);t(26,82,'Keep the lifts.' if phone else 'Keep the lifts. Change the footwork.',31 if phone else 43,bold=True)
 if phone:t(26,124,'Change the footwork.',31,bold=True)
 t(26,161 if phone else 122,'Actual WIF export and fresh reopening.',16,'#657282')
 y=218 if phone else 195;t(26,y,'THE TIE-UP',14,'#185fbd',True)
 # Physical order is preserved, including unused slot 3.
 if phone:
  for i,r in enumerate(plan['tie_up']):
   yy=y+50+i*64;t(26,yy,'Pedal '+str(r['physical_slot']),21,bold=True);t(150,yy,('Fixed: shaft 1','Free -> shaft 2','Fixed: untied')[i],18)
  y=480
 else:
  for i,r in enumerate(plan['tie_up']):
   x=26+i*390;t(x,y+48,'Pedal '+str(r['physical_slot']),27,bold=True);t(x,y+82,('Fixed to shaft 1','Free, assigned shaft 2','Fixed untied, never pressed')[i],19)
  y=325
 t(26,y,'ALL FOUR PICKS / ORIGINAL ORDER',14,'#185fbd',True)
 # Categorical cells; widths do not represent physical textile dimensions.
 if phone:
  ly=y+64;t(87,ly,'Cloth',16,bold=True);t(236,ly,'Press pedals',16,bold=True);t(26,ly+34,'Pick',13);sx,px,cy,step,sz=89,237,ly+67,78,39
 else:
  ly=y+56;t(174,ly,'Requested cloth',20,bold=True);t(560,ly,'Press physical pedals',20,bold=True);t(26,ly+40,'Pick',16);sx,px,cy,step,sz=180,570,ly+70,60,44
 for j in range(2):t(sx+j*(sz+6)+sz/2,cy-15,'E'+str(j+1),14,anchor='middle')
 for j in range(3):t(px+j*(sz+6)+sz/2,cy-15,str(j+1),14,anchor='middle')
 for i,r in enumerate(plan['picks']):
  yy=cy+i*step
  if i==2:out.append(f'<rect x="18" y="{yy-8}" width="{W-36}" height="{sz+16}" fill="#e6edf5"/>')
  t(26,yy+sz/2+6,str(r['pick']),21,bold=True)
  for j,v in enumerate(check['all8DrawdownCells'][i]):cell('drawdown',i+1,j+1,sx+j*(sz+6),yy,v,sz)
  for j in range(3):cell('press',i+1,j+1,px+j*(sz+6),yy,j+1 in r['physical_slots'],sz)
  if not phone:t(840,yy+28,('Shaft 1','Shaft 2','Pair 1 + 2 required','Rest: no press')[i],21,'#185fbd' if i==2 else '#657282',i==2)
 y=cy+4*step+24;t(26,y,'Filled cloth cell = warp above weft.',14,'#657282');t(26,y+27,'E1 threads shaft 1; E2 threads shaft 2.',14,'#657282')
 y=1134 if phone else 795;t(26,y,'Without pair 1 + 2: Infeasible.',20,'#963c40',True);t(26,y+32,'With pair 1 + 2: Feasible. All lifts retained.',17,'#185fbd',True);t(26,y+72,'Schematic union model; no physical loom approval.',13,'#657282');out.append('</svg>');return '\n'.join(out)+'\n'
for name,phone in [('fixed-footwork',False),('fixed-footwork-mobile',True)]:
 svg=draw(phone);(P/(name+'.svg')).write_text(svg);(P/(name+'.html')).write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sley fixed footwork</title><style>body{margin:0}svg{display:block;max-width:100%;height:auto}</style>'+svg)
