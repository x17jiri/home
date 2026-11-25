"""Survey-based setting-out dimensions and current house levels for C sheets."""

from html import escape
from math import atan2, cos, degrees, hypot, radians, sin, sqrt
from pathlib import Path

from roof_frame_3d import HouseInputs
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points
from survey_points import HOUSE_PLACEMENT


SITE_PARCELS = ('105', '106/1', '103/2')
SETBACK_PARCELS = ('107', '343/146', '104/1', '106/2')
FOREST_PARCEL = '806/16'
FOREST_REFERENCE_POINTS = ('142', '143')
METER_SURVEY_POINT = '14'  # Position identified by the investor.
SITE_BOUNDARY_COLOR = '#40508c'
NN_CONNECTION_COLOR = '#b30032'


def model_map_point(x, y, axes, frame, width, depth, placement=HOUSE_PLACEMENT):
    cx, cy = axes.to_local(*placement.center)
    angle = radians(placement.angle_degrees)
    dx, dy = x-width/2, y-depth/2
    sy, sx = axes.frame.to_survey(cx+cos(angle)*dx-sin(angle)*dy,
                                cy+sin(angle)*dx+cos(angle)*dy)
    return frame.to_local(-sy, -sx)


def house_site_data(axes, frame, source=Path(__file__).with_name('house2.py')):
    g = HouseInputs(source).get
    width, depth = g('HOUSE_WIDTH'), g('HOUSE_DEPTH')
    insulation = g('FACADE_INSULATION_THICKNESS')+g('FACADE_THICKNESS')
    if abs(HOUSE_PLACEMENT.width-width-2*insulation) > .001 or abs(HOUSE_PLACEMENT.depth-depth-2*insulation) > .001:
        raise ValueError('Survey house footprint and current facade dimensions differ; update HOUSE_PLACEMENT')
    pwidth, pheight = g('PURLIN_SIZE')
    plate_width, plate_height = g('WALL_PLATE_SIZE')
    seat = g('BWT')/2-plate_width/2
    purlin = g('PURLIN_X_POSITIONS')[0]-pwidth/2
    plate_top = g('WALL_PLATE_Z')+plate_height/2
    slope = (g('PURLIN_Z')+pheight/2-plate_top)/(purlin-seat)
    floor = g('GROUND_FINISHED_FLOOR_ELEVATION')
    ridge = floor-g('GROUND_FLOOR_THICKNESS')+plate_top+slope*(width/2-seat)+(g('ROOF_TILE_BOTTOM')+g('ROOF_TILE_THICKNESS'))*sqrt(1+slope*slope)
    terrain = []
    for x,y,key in ((0,0,'STREET_EAST'),(width,0,'STREET_WEST'),
                    (width,depth,'GARDEN_WEST'),(0,depth,'GARDEN_EAST')):
        terrain.append(dict(local_m=model_map_point(x,y,axes,frame,width,depth),
                            elevation_bpv=g(f'TERRAIN_{key}_ELEVATION')))
    entry_x = (g('THIRD_ROOM_WALL_CENTER_X')+g('STAIRWAY_WALL_CENTER_X'))/2
    return dict(width_m=width, depth_m=depth, floor_elevation_bpv=floor,
                ridge_elevation_bpv=ridge, chimney_elevation_bpv=ridge+g('CHIMNEY_ABOVE_ROOF'),
                terrain=terrain, nn_entry_local_m=model_map_point(entry_x,-insulation,axes,frame,width,depth))


def boundary_setbacks(house, neighbouring_boundaries):
    result = []
    for parcel, boundary in neighbouring_boundaries.items():
        if boundary.is_empty:
            continue
        first,last = nearest_points(house,boundary)
        result.append(dict(parcel=parcel, distance_m=first.distance(last),
                           endpoints_local_m=[tuple(first.coords[0]),tuple(last.coords[0])]))
    return result


def forest_reference_edge(forest, reference_points):
    """Locate the cadastral forest edge beside the supplied survey points."""
    polygons = forest.geoms if forest.geom_type == 'MultiPolygon' else (forest,)
    segments = [LineString([p,q]) for polygon in polygons
                for p,q in zip(polygon.exterior.coords,list(polygon.exterior.coords)[1:])]
    edge = min(segments,key=lambda line:sum(line.distance(p)**2 for p in reference_points))
    if max(edge.distance(p) for p in reference_points) > 3:
        raise ValueError('The referenced survey points are not beside the forest boundary')
    return edge


def dimension_svg(start, end, label, *, identifier, offset=0, centre=None, color='#333'):
    """Printed-mm dimension; endpoints come from exact geometry, never labels."""
    dx,dy = end[0]-start[0],end[1]-start[1]
    length = hypot(dx,dy)
    if length < .001:
        return ''
    ux,uy = dx/length,dy/length
    nx,ny = -uy,ux
    mid = ((start[0]+end[0])/2,(start[1]+end[1])/2)
    if centre is not None and nx*(mid[0]-centre[0])+ny*(mid[1]-centre[1]) < 0:
        offset = -offset
    a,b = (start[0]+nx*offset,start[1]+ny*offset),(end[0]+nx*offset,end[1]+ny*offset)
    angle = degrees(atan2(dy,dx))
    if angle > 90: angle -= 180
    if angle < -90: angle += 180
    # Put the label above the readable text baseline, regardless of line order.
    tx,ty=(a[0]+b[0])/2,(a[1]+b[1])/2
    text_n = (sin(radians(angle)),-cos(radians(angle)))
    tx+=text_n[0]*1.2;ty+=text_n[1]*1.2
    pieces=[f'<g id="{identifier}" fill="none" stroke="{color}" stroke-width=".18">']
    pieces.append(f'<path d="M{a[0]:.4f},{a[1]:.4f}L{b[0]:.4f},{b[1]:.4f}"/>')
    for original,p in ((start,a),(end,b)):
        if offset:
            extra = .7 if offset > 0 else -.7
            pieces.append(f'<path d="M{original[0]:.4f},{original[1]:.4f}L{p[0]+nx*extra:.4f},{p[1]+ny*extra:.4f}"/>')
        tick=(ux+nx,uy+ny)
        pieces.append(f'<path d="M{p[0]-tick[0]*.65:.4f},{p[1]-tick[1]*.65:.4f}l{tick[0]*1.3:.4f},{tick[1]*1.3:.4f}"/>')
    pieces.append(f'<text x="{tx:.4f}" y="{ty:.4f}" text-anchor="middle" font-size="2" '
                  f'transform="rotate({angle:.4f} {tx:.4f} {ty:.4f})" '
                  'style="fill:#222;stroke:white;stroke-width:.8;paint-order:stroke;stroke-linejoin:round">'
                  f'{escape(label)}</text></g>')
    return ''.join(pieces)


def annotations_svg(*, house, site, setbacks, retaining_wall, levels, corners, meter,
                    paper_local, cars, street_frontage, forest_edge):
    """Coordinate annotations in one north-up map frame; no guessed fire zones."""
    pieces=['<g id="site-annotations">']
    centre=paper_local(*house.centroid.coords[0])
    ring=list(house.exterior.coords)[:-1]
    metadata={'setbacks':setbacks, 'corners':corners,'levels':levels,
              'electric_meter_survey_point':METER_SURVEY_POINT}
    for i,(p,q) in enumerate(zip(ring,[*ring[1:],ring[0]])):
        label=f'{hypot(q[0]-p[0],q[1]-p[1]):.2f}'.replace('.',',')
        pieces.append(dimension_svg(paper_local(*p),paper_local(*q),label,
                                    identifier=f'house-dimension-{i}',offset=3.5,centre=centre))
        x,y=paper_local(*p);vx,vy=x-centre[0],y-centre[1];v=hypot(vx,vy)
        pieces.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r=".45" fill="white" stroke="black" stroke-width=".15"/>')
        pieces.append(f'<text x="{x+vx/v*2.2:.3f}" y="{y+vy/v*2.2:.3f}" text-anchor="middle" font-size="1.9" class="map-label">{chr(65+i)}</text>')
    for row in setbacks:
        p,q=row['endpoints_local_m']
        pieces.append(dimension_svg(paper_local(*p),paper_local(*q),f"{row['distance_m']:.2f}".replace('.',','),
                                    identifier=row.get('identifier',f"setback-{row['parcel'].replace('/','-')}"),
                                    offset=row.get('dimension_offset_mm',0),color='#555'))
    forest_points = [paper_local(*p) for p in forest_edge.coords]
    pieces.append('<polyline id="forest-boundary" points="'+
                  ' '.join(f'{x:.3f},{y:.3f}' for x,y in forest_points)+
                  '" fill="none" stroke="#345e38" stroke-width=".35"/>')
    mid=forest_edge.interpolate(.5,normalized=True)
    a,b=forest_edge.coords;dx,dy=b[0]-a[0],b[1]-a[1];length=hypot(dx,dy)
    nx,ny=-dy/length,dx/length
    if nx*(mid.x-house.centroid.x)+ny*(mid.y-house.centroid.y)<0:
        nx,ny=-nx,-ny
    x,y=paper_local(mid.x+nx*2.2,mid.y+ny*2.2)
    pieces.append(f'<text id="forest-label" x="{x:.3f}" y="{y:.3f}" text-anchor="middle" '
                  f'font-size="2" class="map-label">Les – p.č. {FOREST_PARCEL}</text>')
    metadata['forest_boundary_local_m']=forest_edge.__geo_interface__
    metadata['forest_parcel']=FOREST_PARCEL
    metadata['forest_reference_survey_points']=FOREST_REFERENCE_POINTS
    # Mark the shortest physical clearance to the surveyed retaining wall.
    p,q=nearest_points(house,retaining_wall)
    metadata['retaining_wall_clearance_m']=p.distance(q)
    x,y=paper_local(*p.coords[0]);xx,yy=paper_local(*q.coords[0])
    pieces.append(f'<path id="retaining-wall-clearance" d="M{x:.3f},{y:.3f}L{xx:.3f},{yy:.3f}" fill="none" stroke="#333" stroke-width=".22"/>')
    pieces.append(f'<text x="{x+7:.3f}" y="{y-5:.3f}" font-size="1.8" class="map-label">Opěrná zeď: {p.distance(q):.2f} m</text>')
    pieces.append(f'<path d="M{x+7:.3f},{y-4:.3f}L{x:.3f},{y:.3f}" fill="none" stroke="#333" stroke-width=".15"/>')
    # Site/working boundary is confined to the three investor-owned parcels.
    polygons=site.geoms if site.geom_type=='MultiPolygon' else (site,)
    for polygon in polygons:
        points=' '.join(f'{x:.3f},{y:.3f}' for x,y in (paper_local(*p) for p in polygon.exterior.coords))
        pieces.append(f'<polyline class="site-boundary" points="{points}" fill="none" stroke="{SITE_BOUNDARY_COLOR}" stroke-width=".45" stroke-dasharray="2,.8"/>')
    # Proposed cable route: schematic from the existing pillar to the facade.
    start=paper_local(*meter);end=paper_local(*levels['nn_entry_local_m'])
    pieces.append(f'<path id="proposed-nn-connection" d="M{start[0]:.3f},{start[1]:.3f}L{end[0]:.3f},{end[1]:.3f}" fill="none" stroke="{NN_CONNECTION_COLOR}" stroke-width=".5" stroke-dasharray="2,.8"/>')
    pieces.append(f'<rect id="existing-meter-pillar" x="{start[0]-1:.3f}" y="{start[1]-1:.3f}" width="2" height="2" fill="white" stroke="{NN_CONNECTION_COLOR}" stroke-width=".3"/>')
    pieces.append(f'<text x="{start[0]+2:.3f}" y="{start[1]-2:.3f}" font-size="2" class="map-label">Stávající ER</text>')
    metadata['proposed_nn_route_local_m']=[meter,levels['nn_entry_local_m']]
    # Existing road access is marked at the two previously specified gate gaps.
    accesses=[]
    for i,(car,distance) in enumerate(zip(cars,(2.,street_frontage.length-2.)),1):
        gate=street_frontage.interpolate(distance)
        # Match cars to gates by distance instead of depending on frontage order.
        car=min(cars,key=lambda c:Point(c['centre_local_m']).distance(gate))
        ux,uy=car['forward'];origin=gate.coords[0]
        a=paper_local(origin[0]-ux*1.6,origin[1]-uy*1.6)
        b=paper_local(origin[0]+ux*1.6,origin[1]+uy*1.6)
        pieces.append(f'<path id="existing-access-{i}" d="M{a[0]:.3f},{a[1]:.3f}L{b[0]:.3f},{b[1]:.3f}" fill="none" stroke="#222" stroke-width=".4" marker-end="url(#site-arrow)"/>')
        accesses.append(tuple(origin))
    metadata['existing_accesses_local_m']=accesses
    # Design terrain levels come from the same parameters as the house cuts.
    for i,row in enumerate(levels['terrain']):
        x,y=paper_local(*row['local_m']);vx,vy=x-centre[0],y-centre[1];v=hypot(vx,vy)
        x+=vx/v*8;y+=vy/v*8
        pieces.append(f'<text id="design-terrain-{i}" x="{x:.3f}" y="{y:.3f}" text-anchor="middle" font-size="1.8" class="map-label">ÚT {row["elevation_bpv"]:.2f}</text>')
    x,y=centre
    for dy,label in ((-3,'SO 01 – RD'),(1,f"±0,000 = {levels['floor_elevation_bpv']:.3f}"),
                     (5,f"Hřeben {levels['ridge_elevation_bpv']:.3f}")):
        pieces.append(f'<text x="{x:.3f}" y="{y+dy:.3f}" text-anchor="middle" font-size="2" font-weight="bold" class="map-label">{label}</text>')
    pieces.append('</g>')
    return ''.join(pieces),metadata
