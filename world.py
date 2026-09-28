"""Campus Crisis simulation: A*, roles, fog, multi-student rescue."""
from dataclasses import dataclass
import heapq
import math
import json
import random
from pathlib import Path

TILE=32; COLS,ROWS=28,20
BUILDINGS=[(1,1,8,4,'ADMIN BLOCK'),(14,1,7,4,'LIBRARY'),(1,7,9,4,'SCIENCE LAB'),(16,7,6,4,'LECTURE HALL'),(1,13,9,4,'HOSTEL'),(12,13,8,4,'CAFETERIA'),(21,13,6,5,'SPORTS COURT')]
WALLS={(x,y) for bx,by,w,h,_ in BUILDINGS for x in range(bx,bx+w) for y in range(by,by+h)}
SAFE=(3,17,5,3)
# Logical campus landmarks. They anchor resource placement and appear on the map.
LANDMARKS=[('CLINIC',(10,12,2,2),'medkit'),('SECURITY',(25,5,2,3),'ammo'),('GENERATOR',(10,17,2,2),'fuel'),('PARKING',(22,1,5,4),'parking')]
def center(c): return ((c[0]+.5)*TILE,(c[1]+.5)*TILE)
def cell(p): return (int(p[0]//TILE),int(p[1]//TILE))
def in_safe_zone(p):
    """Return whether a world position is inside the evacuation sanctuary."""
    x,y=cell(p)
    return SAFE[0] <= x < SAFE[0]+SAFE[2] and SAFE[1] <= y < SAFE[1]+SAFE[3]
def walkable(p):
    """Outdoor campus routes; the fenced map edge and buildings are inaccessible."""
    x, y = p
    in_safe_zone = SAFE[0] <= x < SAFE[0]+SAFE[2] and SAFE[1] <= y < SAFE[1]+SAFE[3]
    return ((1 <= x < COLS-1 and 1 <= y < ROWS-1) or in_safe_zone) and p not in WALLS
def pathfind(start,goal):
    if not walkable(start) or not walkable(goal): return []
    frontier=[(0,start)]; cost={start:0}; came={}
    while frontier:
        _,cur=heapq.heappop(frontier)
        if cur==goal:
            out=[]
            while cur!=start: out.append(cur); cur=came[cur]
            return out[::-1]
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
            nxt=(cur[0]+dx,cur[1]+dy); score=cost[cur]+1
            if walkable(nxt) and score<cost.get(nxt,math.inf):
                cost[nxt]=score; came[nxt]=cur
                heapq.heappush(frontier,(score+abs(goal[0]-nxt[0])+abs(goal[1]-nxt[1]),nxt))
    return []
@dataclass
class Actor:
    x:float; y:float; role:str; name:str=''; hp:float=100; state:str='Idle'; facing:tuple=(0,1); moving:bool=False; flash:float=0; task:str='Idle'; task_score:int=0; last_seen:tuple|None=None; search_time:float=0; cooldown:float=0; stun:float=0; patrol:int=0; target_name:str=''
    @property
    def pos(self): return (self.x,self.y)
    @property
    def alive(self): return self.hp>0
@dataclass
class Pickup:
    x:float; y:float; kind:str; name:str; discovered:bool=False; collected:bool=False; pulse:float=0
    @property
    def pos(self): return (self.x,self.y)
class Game:
    def __init__(self, seed=None, campaign_level=1, player_role='Commander'):
        self.seed = seed if seed is not None else random.randrange(1, 2**31)
        self.random = random.Random(self.seed)
        self.campaign_level = min(3, max(1, campaign_level))
        self.player_role = player_role
        self.leader=Actor(*center((4,18)),'Leader','Leader'); self.rescuer=Actor(*center((5,18)),'Rescuer','Rescuer'); self.medic=Actor(*center((3,18)),'Medic','Medic'); self.defender=Actor(*center((6,18)),'Defender','Defender'); self.scout=Actor(*center((5,17)),'Scout','Scout')
        missions=(
            {'title':'Campus Evacuation','students':4,'zombies':4,'time':300,'fuel':1,'objective':'Locate and evacuate every stranded student.'},
            {'title':'Emergency Power','students':4,'zombies':4,'time':270,'fuel':2,'objective':'Restore generator fuel, then evacuate every student.'},
            {'title':'Mass Rescue','students':5,'zombies':5,'time':330,'fuel':1,'objective':'Evacuate all students before the outbreak spreads.'},
        )
        base_mission=self.random.choice(missions)
        sector_pressure=self.campaign_level-1
        self.mission={**base_mission,
                      'students':base_mission['students'] + (1 if self.campaign_level == 3 else 0),
                      'zombies':base_mission['zombies'] + sector_pressure,
                      'time':max(180, base_mission['time'] - sector_pressure*30),
                      'sector':self.campaign_level}
        zombie_spawn_pool=((11,3),(13,6),(22,6),(24,10),(11,11),(14,12),(22,11),(10,17),(20,18),(25,9),(10,6),(23,18),(12,1))
        team_start=((4,18),(5,18),(3,18),(6,18),(5,17))
        zombie_spawn_pool=tuple(point for point in zombie_spawn_pool if all(math.dist(point, member) >= 5 for member in team_start))
        rescue_points=((10,3),(13,4),(21,4),(10,8),(15,8),(22,8),(10,10),(15,10),(22,10),(10,15),(11,16),(20,15),(20,17),(25,11))
        # Choose a zombie layout that leaves enough safe, separate positions for
        # every required student. Higher sectors otherwise occasionally created
        # an impossible random mission before the game window could open.
        zombie_spawns=safe_points=None
        for _ in range(80):
            candidate=self.random.sample(zombie_spawn_pool, self.mission['zombies'])
            candidates=[point for point in rescue_points if all(math.dist(point, zombie) >= 3 for zombie in candidate)]
            if len(candidates) >= self.mission['students']:
                zombie_spawns,safe_points=candidate,candidates
                break
        if zombie_spawns is None:
            raise RuntimeError('Unable to generate a safe campus mission layout.')
        selected_points=self.random.sample(safe_points, self.mission['students'])
        self.students=[Actor(*center(c),'Student',f'Student-{i+1}',state='Waiting') for i,c in enumerate(selected_points)]
        self.zombies=[Actor(*center(c),'Zombie',f'Zombie-{i+1}',state='Patrol') for i,c in enumerate(zombie_spawns)]
        resource_sites={
            'medkit':(('Clinic Medkit',(10,12)),('Hostel First-Aid Kit',(10,16)),('Cafeteria Medkit',(20,12))),
            'ammo':(('Security Ammo',(25,6)),('Admin Security Locker',(10,4)),('Sports Equipment Locker',(20,17))),
            'fuel':(('Generator Fuel',(10,18)),('Parking Fuel Can',(22,5)),('Science Lab Fuel',(10,11))),
        }
        selected_resources=[]
        for kind, sites in resource_sites.items():
            selected_resources.extend((kind,point,name) for name,point in self.random.sample(sites, 2))
        self.pickups=[Pickup(*center(point),kind,name) for kind,point,name in selected_resources]
        self.student,self.zombie=self.students[0],self.zombies[0]; self.actors=[self.leader,self.rescuer,self.medic,self.defender,self.scout,*self.students,*self.zombies]
        # In a field-role mission the player is part of an autonomous rescue
        # unit, so the AI Rescuer begins acting on Scout intelligence at once.
        # Commander mode keeps the explicit Follow order for player direction.
        base_scout_points=[(11,2),(22,3),(11,8),(23,8),(11,15),(20,15),(25,11)]
        # Cover every outdoor part of the campus. The former short list could
        # clear its own patrol stops while leaving a survivor hidden elsewhere.
        grid_scout_points=[(x,y) for y in range(2,ROWS-1,4) for x in range(2,COLS-1,4) if walkable((x,y))]
        self.time=float(self.mission['time']); self.elapsed=0.; self.result=None; self.order='Follow' if player_role=='Commander' else 'Rescue'; self.escort_student=None; self.defender_target=None; self.medkits=max(1,3-sector_pressure); self.ammo=20; self.fuel=0; self.fuel_required=self.mission['fuel']; self.shove_cooldown=0; self.routes={}; self.scout_points=list(dict.fromkeys(base_scout_points+grid_scout_points)); self.scout_point=0; self.revealed=set()
        for zombie in self.zombies: zombie.hp += sector_pressure*12
        self.discovered={'Student':False,'Zombie':False,**{a.name:False for a in (*self.students,*self.zombies)}}; self.reveal(self.leader.pos,2.5); self.reveal(self.scout.pos,3); self.logs=[self.mission['title']+': '+self.mission['objective'],'Scout: searching unexplored campus sectors.','Queue the rescue order with E.']
        self.stats={'students_rescued':0,'zombies_neutralized':0,'medkits_used':0,'damage_taken':0,'task_changes':0}
    @property
    def rescued_count(self): return sum(s.state=='Rescued' for s in self.students)
    def log(self,msg): self.logs=(self.logs+[msg])[-6:]
    def collect(self,pickup,collector):
        pickup.collected=True; pickup.pulse=.45
        if pickup.kind=='medkit': self.medkits+=1
        elif pickup.kind=='ammo': self.ammo+=6
        else: self.fuel+=1
        self.log(f'{collector.role}: collected {pickup.kind}.')
    def save_stats(self):
        record={**self.stats,'outcome':self.result,'time_remaining':round(self.time,1),'fuel':self.fuel,'ammo':self.ammo,'mission':self.mission['title'],'sector':self.campaign_level,'students_required':len(self.students),'zombies_deployed':len(self.zombies),'fuel_required':self.fuel_required}
        path=Path(__file__).parent/'logs'/'mission_history.json'; path.parent.mkdir(exist_ok=True)
        history=json.loads(path.read_text()) if path.exists() else []; history.append(record); path.write_text(json.dumps(history,indent=2))
    def task_score(self,p,s,d,r=0): return round(p+s-d/24-r)
    def assign(self,a,task,score,msg):
        a.state,a.task_score=task,score
        if a.task!=task: a.task=task; self.stats['task_changes']+=1; self.log(f'{a.role}: {msg} [score {score}]')
    def command(self,order):
        if not self.result and self.rescuer.alive: self.order=order; self.log({'Rescue':'Rescuer: rescue queue active; awaiting Scout intel.','Follow':'Rescuer: following Commander.','Hold':'Rescuer: holding position.'}[order])
    def controlled_actor(self):
        """Return the field character controlled by the player for this mission."""
        return {'Commander':self.leader, 'Rescuer':self.rescuer, 'Medic':self.medic,
                'Defender':self.defender, 'Scout':self.scout}[self.player_role]
    def player_action(self):
        """Context action for the selected player role, activated with E."""
        a=self.controlled_actor()
        if not a.alive or self.result:return
        pickup=min((p for p in self.pickups if p.discovered and not p.collected and math.dist(a.pos,p.pos)<38), key=lambda p:math.dist(a.pos,p.pos), default=None)
        if pickup:
            self.collect(pickup,a); return
        if self.player_role=='Rescuer':
            if self.escort_student:
                if self.evacuate_escort_if_safe(): return
                self.log(f'Rescuer: escorting {self.escort_student.name} to the Safe Zone.'); return
            student=min((s for s in self.students if s.state=='Waiting' and self.discovered[s.name] and math.dist(a.pos,s.pos)<46), key=lambda s:math.dist(a.pos,s.pos), default=None)
            if student:
                student.state='Following';self.escort_student=student;self.log(f'{student.name}: contact established. Escort them to the Safe Zone.')
            else:self.log('Rescuer: move close to a Scout-located student to begin an escort.')
        elif self.player_role=='Medic':
            patient=min((p for p in (self.leader,self.rescuer,self.defender,self.scout,*self.students) if p.alive and p.state!='Rescued' and p.hp<100 and math.dist(a.pos,p.pos)<48), key=lambda p:p.hp, default=None)
            if patient and self.medkits and not a.cooldown:
                patient.hp=min(100,patient.hp+38);patient.flash=.35;self.medkits-=1;self.stats['medkits_used']+=1;a.cooldown=3;self.log(f'Medic: {patient.name} stabilized. {self.medkits} medkit(s) remain.')
            else:self.log('Medic: move close to an injured teammate and press E to treat them.')
        elif self.player_role=='Defender':
            zombie=min((z for z in self.zombies if z.alive and math.dist(a.pos,z.pos)<92 and self.visible(a.pos,z.pos)), key=lambda z:math.dist(a.pos,z.pos), default=None)
            if zombie and self.ammo and not a.cooldown:
                self.defender_target=zombie;a.state='Engage';a.task=f'Protect Team from {zombie.name}'
                zombie.hp=max(0,zombie.hp-18);zombie.flash=.25;a.cooldown=.5;self.ammo-=1;self.stats['zombies_neutralized']+=int(not zombie.alive);self.log(f'Defender: {zombie.name} neutralized.' if not zombie.alive else f'Defender: engaging {zombie.name}.')
            else:self.log('Defender: move within range of a visible zombie and press E.')
        elif self.player_role=='Scout':
            self.scout_observe(a,4.4);self.log('Scout: scanning the nearby campus sector.')
        else:self.shove()
    def reveal(self,pos,radius):
        o=cell(pos)
        for y in range(max(0,o[1]-4),min(ROWS,o[1]+5)):
            for x in range(max(0,o[0]-4),min(COLS,o[0]+5)):
                if math.dist((x,y),o)<=radius:self.revealed.add((x,y))
    def discover(self,a,msg):
        if not self.discovered[a.name]: self.discovered[a.name]=True; self.discovered[a.role]=True; self.log('Scout: '+msg)
    def clear_at(self,x,y): return all(walkable(cell((x+dx,y+dy))) for dx in (-9,9) for dy in (-9,9))
    def move(self,a,dx,dy):
        before=a.pos
        if self.clear_at(a.x+dx,a.y):a.x+=dx
        if self.clear_at(a.x,a.y+dy):a.y+=dy
        # Ignore sub-pixel collision corrections so an idle agent does not keep
        # triggering the walk animation and appear to vibrate in place.
        a.moving=math.dist(before,a.pos)>.25
        if a.moving:
            n=math.hypot(dx,dy); a.facing=(dx/n,dy/n)
    def navigate(self,a,dest,speed,dt,stop=5):
        if math.dist(a.pos,dest)<stop:return
        start,end=cell(a.pos),cell(dest); route=pathfind(start,end); self.routes[a.name]=route
        if start==end: target=dest
        elif not route:return
        else:
            here,nxt=center(start),center(route[0]); target=here if ((nxt[0]!=here[0] and abs(a.y-here[1])>1) or (nxt[1]!=here[1] and abs(a.x-here[0])>1)) else nxt
        dx,dy=target[0]-a.x,target[1]-a.y; dist=math.hypot(dx,dy)
        if dist:self.move(a,dx/dist*min(speed*dt,dist),dy/dist*min(speed*dt,dist))
    def visible(self,a,b):
        steps=max(1,int(math.dist(a,b)/6)); return all(walkable(cell((a[0]+(b[0]-a[0])*i/steps,a[1]+(b[1]-a[1])*i/steps))) for i in range(steps+1))
    def nearest(self,pos): return min((z for z in self.zombies if z.alive),key=lambda z:math.dist(pos,z.pos),default=None)
    def shove(self):
        if self.result or self.shove_cooldown:return
        self.shove_cooldown=.65; z=min((z for z in self.zombies if z.alive and math.dist(z.pos,self.leader.pos)<64 and self.visible(z.pos,self.leader.pos)),key=lambda z:math.dist(z.pos,self.leader.pos),default=None)
        if z:z.hp=max(0,z.hp-34); z.flash=.25; z.stun=.5; z.state='Stunned' if z.alive else 'Dead'; self.log('Commander: zombie neutralized.' if not z.alive else 'Commander: zombie stunned!')
    def scout_unseen_coverage(self, point):
        """Return how many walkable fog tiles a Scout can reveal from a sector."""
        return sum(
            walkable((x,y)) and (x,y) not in self.revealed and math.dist((x,y),point)<=3.6
            for y in range(max(0,point[1]-4),min(ROWS,point[1]+5))
            for x in range(max(0,point[0]-4),min(COLS,point[0]+5))
        )
    def choose_scout_sector(self, pos, exclude=None):
        """Prefer unexplored fog, then prefer the closest route to it."""
        candidates=[i for i in range(len(self.scout_points)) if i != exclude] or list(range(len(self.scout_points)))
        return max(candidates, key=lambda i: (self.scout_unseen_coverage(self.scout_points[i]), -math.dist(pos,center(self.scout_points[i]))))
    def scout_ai(self,dt):
        a=self.scout
        if not a.alive:
            a.state='Down'; a.task='Down'; return
        danger=self.nearest(a.pos)
        remaining_fog=max(self.scout_unseen_coverage(point) for point in self.scout_points)
        # Use hysteresis: a Scout that spots danger commits to its retreat instead
        # of flipping between Explore and Avoid at the exact vision boundary.
        if danger and math.dist(a.pos,danger.pos)<96 and self.visible(a.pos,danger.pos):
            if a.task != 'Avoid Zombie':
                # Do not repeatedly re-enter the same dangerous sector.
                self.scout_point=self.choose_scout_sector(a.pos,exclude=self.scout_point)
            a.cooldown=2.0
        if a.cooldown>0: self.assign(a,'Avoid Zombie',self.task_score(80,50,math.dist(a.pos,self.leader.pos)),'danger detected; returning to Commander'); self.navigate(a,self.leader.pos,124,dt,52)
        elif remaining_fog == 0:
            # All planned sectors are clear. A fixed patrol target would now be
            # arbitrary and causes route switching, so the Scout rejoins the team.
            self.assign(a,'Report to Commander',48,'campus search complete; reporting to Commander')
            self.navigate(a,self.leader.pos,104,dt,52)
        else:
            current=self.scout_points[self.scout_point]
            # Once a sector is clear, choose the remaining fog with the largest
            # reveal value. This stops the Scout patrolling already-known ground.
            if self.scout_unseen_coverage(current)<=6 or math.dist(a.pos,center(current))<9:
                self.scout_point=self.choose_scout_sector(a.pos,exclude=self.scout_point)
            dest=center(self.scout_points[self.scout_point]); self.assign(a,f'Explore Sector {self.scout_point+1}',self.task_score(55,55,math.dist(a.pos,dest)),f'exploring sector {self.scout_point+1}'); self.navigate(a,dest,108,dt,7)
        self.scout_observe(a,3.6); self.reveal(self.leader.pos,2.2)
    def scout_observe(self,a,radius=3.6):
        """Apply Scout visibility intelligence for both AI and player control."""
        self.reveal(a.pos,radius)
        for s in self.students:
            if s.state=='Waiting' and math.dist(a.pos,s.pos)<150 and self.visible(a.pos,s.pos):self.discover(s,f'survivor found: {s.name}; transmitting rescue location.')
        for z in self.zombies:
            if z.alive and math.dist(a.pos,z.pos)<170 and self.visible(a.pos,z.pos):self.discover(z,f'{z.name} sighted; sharing threat location.')
        for pickup in self.pickups:
            if not pickup.collected and not pickup.discovered and math.dist(a.pos,pickup.pos)<145 and self.visible(a.pos,pickup.pos):
                pickup.discovered=True; self.log(f'Scout: {pickup.kind} located at {pickup.name}.')
    def leader_ai(self,dt):
        """The Commander becomes an AI coordinator whenever the player chooses a field role."""
        a=self.leader
        if not a.alive:a.state='Down';a.task='Down';return
        # Stay at command post rather than forming a crowd around a field role.
        anchor=center((SAFE[0]+SAFE[2]//2, SAFE[1]+SAFE[3]//2))
        self.assign(a,'Coordinate Team',36,'coordinating the field team')
        self.navigate(a,anchor,94,dt,62)
    def evacuate_escort_if_safe(self):
        """Finish an escort when the Rescuer and survivor reach the Safe Zone."""
        s=self.escort_student
        if not s:return False
        rx,ry=cell(self.rescuer.pos); sx,sy=cell(s.pos)
        rescuer_safe=SAFE[0]<=rx<SAFE[0]+SAFE[2] and SAFE[1]<=ry<SAFE[1]+SAFE[3]
        student_safe=SAFE[0]<=sx<SAFE[0]+SAFE[2] and SAFE[1]<=sy<SAFE[1]+SAFE[3]
        if (rescuer_safe and math.dist(self.rescuer.pos,s.pos)<58) or student_safe:
            s.state='Rescued';self.escort_student=None;self.stats['students_rescued']+=1
            self.log(f'{s.name} evacuated. {self.rescued_count}/{len(self.students)} students safe.')
            return True
        return False
    def player_rescuer_update(self,dt):
        if not self.escort_student:return
        s=self.escort_student; self.navigate(s,self.rescuer.pos,94,dt,27)
        self.evacuate_escort_if_safe()
    def rescuer_ai(self,dt):
        r=self.rescuer
        if not r.alive:
            r.state='Down'; r.task='Down'; return
        if self.order=='Rescue':
            if self.escort_student:
                s=self.escort_student; safe_center=center((SAFE[0]+SAFE[2]//2, SAFE[1]+SAFE[3]//2)); self.assign(r,f'Escort {s.name}',95,f'escorting {s.name} to safety'); self.navigate(r,safe_center,88,dt,8); self.navigate(s,r.pos,94,dt,27)
                self.evacuate_escort_if_safe()
            else:
                known=[s for s in self.students if s.state=='Waiting' and self.discovered[s.name]]
                if not known:self.assign(r,'Await Scout Intel',52,'standing by for survivor location')
                else:
                    s=min(known,key=lambda s:math.dist(r.pos,s.pos)); self.assign(r,f'Rescue {s.name}',self.task_score(75,60,math.dist(r.pos,s.pos)),f'dispatched to {s.name}'); self.navigate(r,s.pos,88,dt,8)
                    if math.dist(r.pos,s.pos)<42:s.state='Following';self.escort_student=s;self.log(f'{s.name}: contact established. Returning to Safe Zone.')
        elif self.order=='Follow':self.assign(r,'Follow Commander',30,'following Commander');self.navigate(r,self.leader.pos,104,dt,45)
        else:self.assign(r,'Hold Position',20,'holding position')
    def medic_ai(self,dt):
        m=self.medic
        if not m.alive:
            m.state='Down'; m.task='Down'; return
        patients=[a for a in (self.leader,self.rescuer,self.defender,self.scout,*self.students) if a.alive and a.state!='Rescued' and a.hp<82]
        kits=[p for p in self.pickups if p.kind=='medkit' and p.discovered and not p.collected]
        if self.medkits==0 and kits:
            pickup=min(kits,key=lambda p:math.dist(m.pos,p.pos));self.assign(m,f'Collect {pickup.name}',65,'restocking medical supplies');self.navigate(m,pickup.pos,100,dt,18)
            if math.dist(m.pos,pickup.pos)<20:self.collect(pickup,m)
            return
        if patients and self.medkits:
            p=min(patients,key=lambda a:a.hp); self.assign(m,f'Heal {p.name}',self.task_score(100-p.hp,48,math.dist(m.pos,p.pos)),f'treating {p.name}');self.navigate(m,p.pos,100,dt,28)
            if math.dist(m.pos,p.pos)<32 and not m.cooldown:p.hp=min(100,p.hp+38);p.flash=.35;self.medkits-=1;self.stats['medkits_used']+=1;m.cooldown=3;self.log(f'Medic: {p.name} stabilized. {self.medkits} medkit(s) remain.')
        else:
            clinic=center((10,12));self.assign(m,'Stage at Clinic',self.task_score(10,30,math.dist(m.pos,clinic)),'staging at the clinic')
            self.navigate(m,clinic,92,dt,45)
    def defender_ai(self,dt):
        d=self.defender
        if not d.alive:
            d.state='Down'; d.task='Down'; return
        ammo_pickups=[p for p in self.pickups if p.kind=='ammo' and p.discovered and not p.collected]
        if self.ammo<=2 and ammo_pickups:
            p=min(ammo_pickups,key=lambda p:math.dist(d.pos,p.pos));self.assign(d,f'Collect {p.name}',70,'restocking ammunition');self.navigate(d,p.pos,112,dt,16)
            if math.dist(d.pos,p.pos)<20:self.collect(p,d)
            return
        threats=[z for z in self.zombies if z.alive and self.discovered[z.name]]; people=[a for a in (self.leader,self.rescuer,self.scout,*self.students) if a.alive and a.state!='Rescued']
        if threats:
            z=min(threats,key=lambda z:math.dist(d.pos,z.pos)); p=min(people,key=lambda a:math.dist(z.pos,a.pos)); self.defender_target=z; self.assign(d,f'Protect {p.name}',self.task_score(80,55,math.dist(d.pos,z.pos)),f'intercepting {z.name} near {p.name}')
            if math.dist(d.pos,z.pos)>39:self.navigate(d,z.pos,112,dt,28)
            else:
                d.state='Engage'
                if not d.cooldown and self.ammo:z.hp=max(0,z.hp-14);self.ammo-=1;z.flash=.25;d.cooldown=.58;self.stats['zombies_neutralized']+=int(not z.alive);self.log(f'Defender: {z.name} neutralized.' if not z.alive else f'Defender: engaging {z.name}.')
        else:
            safe_center=center((SAFE[0]+SAFE[2]//2, SAFE[1]+SAFE[3]//2));self.assign(d,'Guard Safe Zone',self.task_score(12,45,math.dist(d.pos,safe_center)),'guarding the Safe Zone')
            self.navigate(d,safe_center,96,dt,62)
    def zombie_ai(self,z,dt,sprint):
        if not z.alive or z.stun:
            z.target_name=''
            return
        # The Safe Zone is a guarded sanctuary, not merely the visual point where
        # students are dropped off. A zombie may never deal damage to anybody in
        # it, and it abandons a stale chase that would take it into the sanctuary.
        if in_safe_zone(z.pos):
            z.target_name=''; z.last_seen=None; z.search_time=0; z.state='Retreat'
            self.navigate(z,center((SAFE[0]+SAFE[2]+1, SAFE[1]+SAFE[3]//2)),66,dt,8)
            return
        # Waiting students are concealed in their classrooms. Once a Rescuer makes
        # contact they become an exposed escort target, creating rescue risk
        # without allowing an unseen patrol to end the mission immediately.
        targets=[a for a in (self.leader,self.rescuer,*self.students) if a.alive and a.state!='Rescued' and not in_safe_zone(a.pos) and (a.role != 'Student' or a.state == 'Following') and math.dist(z.pos,a.pos)<(245 if sprint and a is self.leader else 185) and self.visible(z.pos,a.pos)]
        defender_is_player = self.player_role=='Defender'
        defender_engaging = self.defender_target is z and self.defender.state=='Engage'
        # A player Defender is a valid threat target whenever they approach a
        # zombie, even before shooting. AI Defenders are targeted on engagement.
        if self.defender.alive and not in_safe_zone(self.defender.pos) and (defender_engaging or defender_is_player) and math.dist(z.pos,self.defender.pos)<185 and self.visible(z.pos,self.defender.pos):
            targets.append(self.defender)
        if targets:
            # An exposed escorted student is the highest-value target. This makes
            # the rescue threat visible instead of silently redirecting attacks
            # to a nearby Rescuer or Defender.
            escorted=[a for a in targets if a.role=='Student' and a.state=='Following']
            t=min(escorted,key=lambda a:math.dist(z.pos,a.pos)) if escorted else (self.defender if self.defender in targets else min(targets,key=lambda a:math.dist(z.pos,a.pos)));z.target_name=t.name;z.last_seen=t.pos;z.search_time=3
            if math.dist(z.pos,t.pos)<27:
                z.state='Attack'
                if not z.cooldown:
                    t.hp=max(0,t.hp-6);t.flash=.3;z.cooldown=.75
                    if not t.alive:
                        z.target_name=''; z.last_seen=None; z.search_time=0; z.state='Patrol'
            else:z.state='Chase';self.navigate(z,t.pos,76,dt,20)
        elif z.last_seen and not in_safe_zone(z.last_seen):
            z.target_name=''
            z.state='Search';self.navigate(z,z.last_seen,66,dt);z.search_time-=dt
            if z.search_time<=0:z.last_seen=None
        else:
            z.target_name=''
            z.last_seen=None
            z.state='Patrol';pts=[(25,10),(25,2),(14,2),(14,10)];dest=center(pts[(z.patrol+self.zombies.index(z))%4]);self.navigate(z,dest,48,dt)
            if math.dist(z.pos,dest)<6:z.patrol=(z.patrol+1)%4
    def update(self,dt,movement=(0,0),sprint=False):
        if self.result:return
        dt=min(dt,.05);self.elapsed+=dt;self.time=max(0,self.time-dt);self.shove_cooldown=max(0,self.shove_cooldown-dt)
        for a in self.actors:a.moving=False;a.flash=max(0,a.flash-dt);a.cooldown=max(0,a.cooldown-dt);a.stun=max(0,a.stun-dt)
        for pickup in self.pickups: pickup.pulse=max(0,pickup.pulse-dt)
        dx,dy=movement;n=math.hypot(dx,dy)
        player=self.controlled_actor()
        if n and player.alive:self.move(player,dx/n*(158 if sprint else 112)*dt,dy/n*(158 if sprint else 112)*dt)
        if self.player_role!='Commander':self.leader_ai(dt)
        if self.player_role!='Scout':self.scout_ai(dt)
        else:
            # A player Scout continuously provides reconnaissance while moving;
            # E is an optional wider scan, not a prerequisite for opening fog.
            self.scout_observe(self.scout,3.6)
            self.reveal(self.leader.pos,2.2)
        if self.player_role!='Rescuer':self.rescuer_ai(dt)
        else:self.player_rescuer_update(dt)
        if self.player_role!='Medic':self.medic_ai(dt)
        if self.player_role!='Defender':self.defender_ai(dt)
        for z in self.zombies:self.zombie_ai(z,dt,sprint)
        if any(not s.alive for s in self.students):self.result='Student lost'
        elif not self.leader.alive or not self.rescuer.alive:self.result='Rescue team lost'
        elif self.time<=0:self.result='Time expired'
        elif self.rescued_count==len(self.students):self.result='Mission complete';self.log('All students evacuated. Campus rescue successful!')
        if self.result:self.save_stats()
