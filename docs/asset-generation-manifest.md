# Genesis asset generation manifest

Original Genesis cozy top-down survival colony pixel art; warm upper-left light, moss greens, amber wood, terracotta and turquoise; crisp pixel clusters, consistent scale, orthographic top-down with small visible south-facing sides; no writing, labels or logos.

Original art was generated through Figma AI (gemini-3.1-flash-lite-image) and saved in the repository. Sources are JPEG; transparent PNGs are produced by inspected background removal and nearest-neighbor assembly. The first action-sheet generation had inconsistent grid/directions and is preserved as rejected source; the integrated animation sheets use the clean directional walk sheet plus deterministic tool/pose assembly.

All shipped sprites are local. No expiring remote URL is used by the app. Replace a PNG at its manifest path to use externally generated alternatives; reload the browser. Missing files use an explicitly marked procedural fallback so the application remains runnable.

| Asset | File | Category | Dimensions | Alpha |
|---|---|---|---|---|
| grass | /assets/genesis/grass.png | terrain | 32×32 | False |
| forest_floor | /assets/genesis/forest_floor.png | terrain | 32×32 | False |
| dirt | /assets/genesis/dirt.png | terrain | 32×32 | False |
| sand | /assets/genesis/sand.png | terrain | 32×32 | False |
| stone_floor | /assets/genesis/stone_floor.png | terrain | 32×32 | False |
| water | /assets/genesis/water.png | terrain | 32×32 | False |
| fertile_soil | /assets/genesis/fertile_soil.png | terrain | 32×32 | False |
| path | /assets/genesis/path.png | terrain | 32×32 | False |
| grass_flowers | /assets/genesis/grass_flowers.png | terrain | 32×32 | False |
| forest_leaves | /assets/genesis/forest_leaves.png | terrain | 32×32 | False |
| dry_grass | /assets/genesis/dry_grass.png | terrain | 32×32 | False |
| mountain_floor | /assets/genesis/mountain_floor.png | terrain | 32×32 | False |
| water_shallow | /assets/genesis/water_shallow.png | terrain | 32×32 | False |
| river_edge | /assets/genesis/river_edge.png | terrain | 32×32 | False |
| valley_grass | /assets/genesis/valley_grass.png | terrain | 32×32 | False |
| planks | /assets/genesis/planks.png | terrain | 32×32 | False |
| oak | /assets/genesis/oak.png | nature/buildings | 64×64 | True |
| pine | /assets/genesis/pine.png | nature/buildings | 64×64 | True |
| berry_bush | /assets/genesis/berry_bush.png | nature/buildings | 64×64 | True |
| flowers | /assets/genesis/flowers.png | nature/buildings | 64×64 | True |
| rock | /assets/genesis/rock.png | nature/buildings | 64×64 | True |
| ore_deposit | /assets/genesis/ore_deposit.png | nature/buildings | 64×64 | True |
| logs | /assets/genesis/logs.png | nature/buildings | 64×64 | True |
| crops | /assets/genesis/crops.png | nature/buildings | 64×64 | True |
| campfire | /assets/genesis/campfire.png | nature/buildings | 64×64 | True |
| shelter | /assets/genesis/shelter.png | nature/buildings | 64×64 | True |
| workbench | /assets/genesis/workbench.png | nature/buildings | 64×64 | True |
| storage | /assets/genesis/storage.png | nature/buildings | 64×64 | True |
| farm | /assets/genesis/farm.png | nature/buildings | 64×64 | True |
| wooden_wall | /assets/genesis/wooden_wall.png | nature/buildings | 64×64 | True |
| stone_wall | /assets/genesis/stone_wall.png | nature/buildings | 64×64 | True |
| watchtower | /assets/genesis/watchtower.png | nature/buildings | 64×64 | True |
| bridge | /assets/genesis/bridge.png | nature/buildings | 64×64 | True |
| road | /assets/genesis/road.png | nature/buildings | 64×64 | True |
| remote_camp | /assets/genesis/remote_camp.png | nature/buildings | 64×64 | True |
| clay_deposit | /assets/genesis/clay_deposit.png | nature/buildings | 64×64 | True |
| coal_pile | /assets/genesis/coal_pile.png | nature/buildings | 64×64 | True |
| fiber_plant | /assets/genesis/fiber_plant.png | nature/buildings | 64×64 | True |
| seed_plant | /assets/genesis/seed_plant.png | nature/buildings | 64×64 | True |
| spring | /assets/genesis/spring.png | nature/buildings | 64×64 | True |
| item_wood | /assets/genesis/item_wood.png | items | 24×24 | True |
| item_stone | /assets/genesis/item_stone.png | items | 24×24 | True |
| item_food | /assets/genesis/item_food.png | items | 24×24 | True |
| item_fiber | /assets/genesis/item_fiber.png | items | 24×24 | True |
| item_clay | /assets/genesis/item_clay.png | items | 24×24 | True |
| item_ore | /assets/genesis/item_ore.png | items | 24×24 | True |
| item_fuel | /assets/genesis/item_fuel.png | items | 24×24 | True |
| item_water_item | /assets/genesis/item_water_item.png | items | 24×24 | True |
| item_seeds | /assets/genesis/item_seeds.png | items | 24×24 | True |
| item_axe | /assets/genesis/item_axe.png | items | 24×24 | True |
| item_pickaxe | /assets/genesis/item_pickaxe.png | items | 24×24 | True |
| item_torch | /assets/genesis/item_torch.png | items | 24×24 | True |
| item_hammer | /assets/genesis/item_hammer.png | items | 24×24 | True |
| item_wheat | /assets/genesis/item_wheat.png | items | 24×24 | True |
| item_sapling | /assets/genesis/item_sapling.png | items | 24×24 | True |
| item_board | /assets/genesis/item_board.png | items | 24×24 | True |
| character_0 | /assets/genesis/character-0.png | characters | 192×1536 | True |
| character_1 | /assets/genesis/character-1.png | characters | 192×1536 | True |
| character_2 | /assets/genesis/character-2.png | characters | 192×1536 | True |
| character_3 | /assets/genesis/character-3.png | characters | 192×1536 | True |

Each JSON entry includes a complete master+subject generation prompt, intended project path, frame layout, perspective and priority. Related outputs are grouped into the four batches above. Generate terrain as seamless 32×32 tiles; nature/buildings as centered 64×64 transparent PNGs; items as 24×24 transparent PNGs. Character replacement sheets must preserve the declared 48×48 cell grid.
