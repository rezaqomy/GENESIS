"""Deterministic atlas assembly from original Figma-generated source art (requires Pillow)."""
import json
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'frontend/public/assets/genesis'
SOURCE=OUT/'source'
RESAMPLE=Image.Resampling.NEAREST
MASTER=('Original Genesis cozy top-down survival colony pixel art; warm upper-left light, '
        'moss greens, amber wood, terracotta and turquoise; crisp pixel clusters, consistent scale, '
        'orthographic top-down with small visible south-facing sides; no writing, labels or logos.')
manifest={"version":2,"tile_size":32,"master_prompt":MASTER,"assets":{},"batches":{}}


def transparent(image):
    image=image.convert('RGBA')
    w,h=image.size
    pixels=image.load()
    corners=[pixels[x,y][:3] for x,y in ((0,0),(w-1,0),(0,h-1),(w-1,h-1),(w//2,0),(w//2,h-1),(0,h//2),(w-1,h//2),(10,10),(w-11,10),(10,h-11),(w-11,h-11))]
    visited=set()
    queue=deque([(x,0) for x in range(w)]+[(x,h-1) for x in range(w)]
                +[(0,y) for y in range(h)]+[(w-1,y) for y in range(h)])
    while queue:
        x,y=queue.popleft()
        if (x,y) in visited or not (0<=x<w and 0<=y<h):
            continue
        visited.add((x,y))
        color=pixels[x,y][:3]
        if min(sum((color[i]-c[i])**2 for i in range(3)) for c in corners)>22**2*3:
            continue
        pixels[x,y]=(0,0,0,0)
        queue.extend(((x+1,y),(x-1,y),(x,y+1),(x,y-1)))
    # Remove detached near-black/white JPEG background noise after flood fill.
    for y in range(h):
        for x in range(w):
            r,g,b,a=pixels[x,y]
            if a and (max(r,g,b)<16 or min(r,g,b)>245):
                pixels[x,y]=(0,0,0,0)
    return image


def fit(image,size,padding=2):
    bbox=image.getbbox()
    canvas=Image.new('RGBA',size)
    if not bbox:
        return canvas
    image=image.crop(bbox)
    ratio=min((size[0]-padding*2)/image.width,(size[1]-padding*2)/image.height)
    image=image.resize((max(1,round(image.width*ratio)),max(1,round(image.height*ratio))),RESAMPLE)
    canvas.alpha_composite(image,((size[0]-image.width)//2,size[1]-image.height-padding))
    return canvas


def record(asset_id,filename,category,size,transparent_bg=True,frames=None,source=None):
    manifest['assets'][asset_id]={"id":asset_id,"file":f"/assets/genesis/{filename}",
        "category":category,"width":size[0],"height":size[1],"transparent":transparent_bg,
        "frames":frames,"perspective":"top-down","art_style":"pixel-art",
        "priority":"required","prompt":MASTER+f' Subject: {asset_id.replace("_"," ")}.',
        "source":source,"status":"generated-and-assembled"}


def atlas(source,columns,rows,names,size,category,alpha):
    image=Image.open(SOURCE/source)
    for i,name in enumerate(names):
        x,y=i%columns,i//columns
        margin=4 if alpha else 0
        cell=image.crop((round(x*image.width/columns)+margin,round(y*image.height/rows)+margin,
                         round((x+1)*image.width/columns)-margin,round((y+1)*image.height/rows)-margin))
        cell=fit(transparent(cell),size) if alpha else cell.resize(size,RESAMPLE).convert('RGBA')
        filename=f'{name}.png'
        cell.save(OUT/filename,optimize=True)
        record(name,filename,category,size,alpha,source=source)


terrain=['grass','forest_floor','dirt','sand','stone_floor','water','fertile_soil','path',
         'grass_flowers','forest_leaves','dry_grass','mountain_floor','water_shallow','river_edge',
         'valley_grass','planks']
atlas('terrain-v2.jpg',4,4,terrain,(32,32),'terrain',False)
objects=['oak','pine','berry_bush','flowers','rock','ore_deposit','logs','crops','campfire',
         'shelter','workbench','storage','farm','wooden_wall','stone_wall','watchtower','bridge',
         'road','remote_camp','clay_deposit','coal_pile','fiber_plant','seed_plant','spring']
atlas('objects-v2.jpg',6,4,objects,(64,64),'nature/buildings',True)
items=['wood','stone','food','fiber','clay','ore','fuel','water_item','seeds','axe','pickaxe',
       'torch','hammer','wheat','sapling','board']
atlas('items-v2.jpg',4,4,[f'item_{n}' for n in items],(24,24),'items',True)

walk=Image.open(SOURCE/'walk-v2.jpg')
actions=['idle','walk','gather','mine','build','craft','rest','social']
# The first requested action atlas contained inconsistent cells. Use inspected clean walk
# cells as directional bases and deterministically assemble action props/poses instead.
variants=['#df9272','#7eabc5','#b39bc9','#dbbb70']
for variant,color in enumerate(variants):
    sheet=Image.new('RGBA',(4*48,4*len(actions)*48))
    rgb=tuple(int(color[i:i+2],16) for i in (1,3,5))
    for direction in range(4):
        for frame in range(4):
            row=direction if direction<3 else 2
            col=frame if direction<2 else frame%2
            cell=walk.crop((col*256+6,row*256+6,(col+1)*256-6,(row+1)*256-6))
            base=fit(transparent(cell),(24,34),padding=1)
            if direction==3:
                base=ImageOps.mirror(base)
            pixels=base.load()
            for y in range(base.height):
                for x in range(base.width):
                    r,g,b,a=pixels[x,y]
                    if a and g>r*1.18 and b>r*1.05:
                        light=(r+g+b)/(3*100)
                        pixels[x,y]=tuple(min(255,round(v*light)) for v in rgb)+(a,)
                    elif a and y<base.height*.35 and r>g*1.2 and r<130:
                        pixels[x,y]=(min(255,r+variant*8),max(0,g-variant*2),b,a)
            for action_index,action in enumerate(actions):
                canvas=Image.new('RGBA',(48,48))
                dy=1 if frame%2 and action in ('walk','gather','build','craft') else 0
                body=base.copy()
                if action=='rest':
                    body=body.crop((0,0,24,27))
                    dy=6
                canvas.alpha_composite(body,(12,10+dy))
                if action in ('gather','mine','build','craft'):
                    item={'gather':'food','mine':'pickaxe','build':'hammer','craft':'axe'}[action]
                    prop=Image.open(OUT/f'item_{item}.png').resize((13,13),RESAMPLE)
                    prop=prop.rotate((-25 if frame%2 else 20),resample=RESAMPLE,expand=True)
                    canvas.alpha_composite(prop,(25 if direction!=2 else 5,15+(frame%2)*3))
                if action=='social':
                    draw=ImageDraw.Draw(canvas)
                    draw.rectangle((31,15-(frame%2)*4,34,21-(frame%2)*4),fill=rgb+(255,))
                    draw.rectangle((31,12-(frame%2)*4,34,15-(frame%2)*4),fill=(226,178,137,255))
                sheet.alpha_composite(canvas,(frame*48,(direction*len(actions)+action_index)*48))
    filename=f'character-{variant}.png'
    sheet.save(OUT/filename,optimize=True)
    record(f'character_{variant}',filename,'characters',sheet.size,frames={
        'cell_width':48,'cell_height':48,'directions':['south','north','west','east'],
        'actions':actions,'frames_per_action':4},source='walk-v2.jpg + generated item props')
manifest['batches']={
 'terrain':{'source':'source/terrain-v2.jpg','grid':[4,4]},
 'objects':{'source':'source/objects-v2.jpg','grid':[6,4]},
 'items':{'source':'source/items-v2.jpg','grid':[4,4]},
 'characters':{'source':'source/walk-v2.jpg','grid':[4,4],
               'assembly':'Recolor clothing/hair; normalize 4 directions; add generated tools and poses for 8 actions.'}}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(ROOT/'docs/asset-generation-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
lines=['# Genesis asset generation manifest','',MASTER,'',
 'Original art was generated through Figma AI (gemini-3.1-flash-lite-image) and saved in the repository. '+
 'Sources are JPEG; transparent PNGs are produced by inspected background removal and nearest-neighbor assembly. '+
 'The first action-sheet generation had inconsistent grid/directions and is preserved as rejected source; '+
 'the integrated animation sheets use the clean directional walk sheet plus deterministic tool/pose assembly.',
 '', 'All shipped sprites are local. No expiring remote URL is used by the app. '+
 'Replace a PNG at its manifest path to use externally generated alternatives; reload the browser. '+
 'Missing files use an explicitly marked procedural fallback so the application remains runnable.', '',
 '| Asset | File | Category | Dimensions | Alpha |','|---|---|---|---|---|']
for a in manifest['assets'].values():
    lines.append(f'| {a["id"]} | {a["file"]} | {a["category"]} | {a["width"]}×{a["height"]} | {a["transparent"]} |')
lines += ['', 'Each JSON entry includes a complete master+subject generation prompt, intended project path, '+
          'frame layout, perspective and priority. Related outputs are grouped into the four batches above. '+
          'Generate terrain as seamless 32×32 tiles; nature/buildings as centered 64×64 transparent PNGs; '+
          'items as 24×24 transparent PNGs. Character replacement sheets must preserve the declared 48×48 cell grid.']
(ROOT/'docs/asset-generation-manifest.md').write_text('\n'.join(lines)+'\n')
print(f'Assembled {len(manifest["assets"])} original asset files.')
