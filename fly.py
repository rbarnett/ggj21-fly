from __future__ import division, print_function, unicode_literals

# This code is so you can run the samples without installing the package
import sys
import os
#sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
#

import random
import math

import pyglet
from pyglet.window import key
from pyglet.gl import *

import cocos
from cocos.director import director
import cocos.collision_model as cm
import cocos.euclid as eu
import cocos.actions as ac
from cocos import draw
    
consts = {
    "window": {
        "width": 800,
        "height": 600,
        "vsync": True,
        "resizable": True
    },
    "world": {
        "width": 400,
        "height": 300,
        "rPlayer": 8.0,
        "wall_scale_min": 0.75,  # relative to player
        "wall_scale_max": 2.25,  # relative to player
        "topSpeed": 100.0,
        "angular_velocity": 300.0,  # degrees / s
        "accel": 200.0,
        "bindings": {
            key.LEFT: 'left',
            key.RIGHT: 'right',
            key.UP: 'up',
        }
    },
    "view": {
        # as the font file is not provided it will decay to the default font;
        # the setting is retained anyway to not downgrade the code
        "font_name": 'Arial Black',
        "palette": {
            'bg': (180, 180, 250),
            'player': (255, 255, 255),
            'wall': (247, 148, 29),
            'gate': (140, 198, 62),
            'pad': (170, 220, 170),
            'special': (30, 30, 30)
        }
    }
}

# world to view scales
scale_x = consts["window"]["width"] / consts["world"]["width"]
scale_y = consts["window"]["height"] / consts["world"]["height"]

# view to world scales
inv_scale_x = consts["world"]["width"] / consts["window"]["width"]
inv_scale_y = consts["world"]["height"] / consts["window"]["height"]


def world_to_view(v):
    """world coords to view coords; v an eu.Vector2, returns (float, float)"""
    return v.x * scale_x, v.y * scale_y
    
def view_to_world(x, y):
    """world coords to view coords; v an eu.Vector2, returns (float, float)"""
    return x * inv_scale_x, y * inv_scale_y


class Actor(cocos.sprite.Sprite):
    palette = {}  # injected later

    def __init__(self, cx, cy, radius, btype, img, vel=None):
        super(Actor, self).__init__(img)
        # the 1.05 so that visual radius a bit greater than collision radius
        self.scale = (radius * 1.05) * scale_x / (self.image.width / 2.0)
        self.btype = btype
        self.color = self.palette[btype]
        self.cshape = cm.CircleShape(eu.Vector2(cx, cy), radius)
        self.update_center(self.cshape.center)
        if vel is None:
            vel = eu.Vector2(0.0, 0.0)
        self.vel = vel

    def update_center(self, cshape_center):
        """cshape_center must be eu.Vector2"""
        self.position = world_to_view(cshape_center)
        self.cshape.center = cshape_center


class MessageLayer(cocos.layer.Layer):

    """Transitory messages over worldview

    Responsability:
    full display cycle for transitory messages, with effects and
    optional callback after hiding the message.
    """

    def show_message(self, msg, callback=None):
        w, h = director.get_window_size()

        self.msg = cocos.text.Label(msg,
                                    font_size=52,
                                    font_name=consts['view']['font_name'],
                                    anchor_y='center',
                                    anchor_x='center',
                                    width=w,
                                    multiline=True,
                                    align="center")
        self.msg.position = (w / 2.0, h)

        self.add(self.msg)

        actions = (
            ac.Show() + ac.Accelerate(ac.MoveBy((0, -h / 2.0), duration=0.5)) +
            ac.Delay(1) +
            ac.Accelerate(ac.MoveBy((0, -h / 2.0), duration=0.5)) +
            ac.Hide()
        )

        if callback:
            actions += ac.CallFunc(callback)

        self.msg.do(actions)
        
    def show_label(self, label):
        self.add(label)    


def reflection_y(a):
    assert isinstance(a, eu.Vector2)
    return eu.Vector2(a.x, -a.y)


class Worldview(cocos.layer.Layer):

    """
    Responsibilities:
        Generation: random generates a level
        Initial State: Set initial playststate
        Play: updates level state, by time and user input. Detection of
        end-of-level conditions.
        Level progression.
    """
    is_event_handler = True

    def __init__(self, fn_show_message=None, fn_show_label=None):
        super(Worldview, self).__init__()
        self.fn_show_message = fn_show_message
        self.fn_show_label = fn_show_label

        # basic geometry
        world = consts['world']
        self.width = world['width']  # world virtual width
        self.height = world['height']  # world virtual height
        self.rPlayer = world['rPlayer']  # player radius in virtual space
        self.wall_scale_min = world['wall_scale_min']
        self.wall_scale_max = world['wall_scale_max']
        self.topSpeed = world['topSpeed']
        self.angular_velocity = world['angular_velocity']
        self.accel = world['accel']

        # load resources:
        pics = {}
        pics["player"] = pyglet.resource.image('fly.png')
        pics["pad"] = pyglet.resource.image('circle6.png')
        pics["wall"] = pyglet.resource.image('circle6.png')
        self.pics = pics

        cell_size = self.rPlayer * self.wall_scale_max * 2.0 * 1.25

        self.bindings = world['bindings']
        buttons = {}
        for k in self.bindings:
            buttons[self.bindings[k]] = 0
        self.buttons = buttons
        self.upButtonReleased = True

        self.schedule(self.update)
        self.ladder_begin()
        
        self.specialPads = []
        self.specialPadMessageDecay = 0.0
        
        self.backgroundLabelCount = 0
        self.lastCompliment = ""
        

    def ladder_begin(self):
        self.level_num = 0
        self.empty_level()
        msg = 'You are pretty fly'
        self.fn_show_message(msg, callback=self.level_launch)

    def level_launch(self):
        self.generate_level()
        #self.generate_random_level()
        #msg = 'level %d' % self.level_num
        #self.fn_show_message(msg, callback=self.level_start)
        self.level_start()

    def level_start(self):
        self.win_status = 'undecided'

    def level_complete(self):
        self.win_status = 'complete'
        
        for child in self.get_children():
            if child.btype == "pad":
                child.stop()
                child.do(ac.FadeOut(1))
                
        self.do(ac.Delay(15) + ac.CallFunc(self.ladder_begin))
            
            
        # msg = 'level %d\nconquered !' % self.level_num
        # self.fn_show_message(msg, callback=self.level_next)

    def level_lost(self):
        self.win_status = 'lost'
        msg = 'You flew away!'
        self.fn_show_message(msg, callback=self.ladder_begin)

    def level_next(self):
        self.empty_level()
        self.level_num += 1
        self.level_launch()

    def empty_level(self):
        # del old actors, if any
        for node in self.get_children():
            self.remove(node)
        assert len(self.children) == 0
        self.player = None
        self.gate = None
        self.pad_cnt = 0
        
        self.specialPads = []
        self.specialPadMessageDecay = 0.0
        self.backgroundLabelCount = 0
        
        self.swipeDecay = 0.0
        self.swipeAngle = 0.0
        self.swipePads = []
        
        self.compliments = [
            "You are superb",
            "You are #winning",
            "You are tenacious",
            "You are amazing",
            "You are pretty fly",
            "You are brilliant",
            "You are incredible",
            "You are dependable",
            "You are reliable",
            "You are sunshine",
            "You are awesome",
            "You are smart",
            "You are dedicated",
            "You are impeccable",
            "You are strong",
            "You are refreshing",
            "You are deserving",
            "You are helpful",
            "You are courageous",
            "You are funny",
            "You are kind",
            "You are great",
            "You are joyful",
            "You are wonderful",
            "You are interesting",
            "You are one of a kind",
            "You are unique",
            "You are fun",
            "You are thoughtful",
            "You are creative",
            "You are trustworthy",
            "You are lovely",
            "You are stylish",
            "You are special",
            "You are inspiring",
            "You are brave",
            "You are charming",
            "You are adorable",
            "You are magnificent",
            "You are generous",
            "You are impressive",
            "You are positive",  
            "You are superlative",                        
        ]

        self.win_status = 'intermission'  # | 'undecided' | 'complete' | 'lost'

        # player phys params
        self.topSpeed = 150.0  # 50.
        self.impulse_dir = eu.Vector2(0.0, 1.0)
        self.impulseForce = 0.0

    def rotatePoint(self, point, origin, angleDeg):
        #Rotate a point counterclockwise by a given angle around a given origin.
        ox, oy = origin.x, origin.y
        px, py = point.x, point.y
        angleRad = math.radians(angleDeg)

        qx = ox + math.cos(angleRad) * (px - ox) - math.sin(angleRad) * (py - oy)
        qy = oy + math.sin(angleRad) * (px - ox) + math.cos(angleRad) * (py - oy)
        return eu.Point2(qx, qy)
        
    def add_pads(self, origin, padSize, radius):
        circumference = math.pi * 2 * radius
        numInCircle = math.floor(circumference / ((padSize * 2.0) + 2.0))
        
        pads = []
        startPoint = eu.Point2(origin.x + radius, origin.y)
        for i in range(0, numInCircle):
            nextPoint = self.rotatePoint(startPoint, origin, (360 / numInCircle) * (i+1))
            pad = Actor(nextPoint.x, nextPoint.y, padSize, 'pad', self.pics['pad'])
            self.add(pad, z=100)
            pad.disabled = False
            pad.special = False
            pad.specialTriggered = False
            pad.spinning = False
            pads.append(pad)
            
        return pads
    

    def generate_level(self):
        # add player
        origin = eu.Point2(0.5 * self.width, 0.5 * self.height)
        self.player = Actor(origin.x, origin.y, self.rPlayer, 'player', self.pics['player'])
        self.player.moveDecay = 0.0
        self.player.currentPad = None
        self.player.disabled = False
        self.player.invincible = False

        self.cnt_pad = 0
        
        padSize = 8.0
        radius = 17.0
        padsExclInner = []
        
        for i in range(1, 9):
            addedPads = self.add_pads(origin, padSize, radius * i)
            if i > 3:
                padsExclInner += addedPads
        
        numSpecialPads = 6
        for i in range(numSpecialPads):
            chosenPad = random.choice(padsExclInner)
            chosenPad.special = True
            self.specialPads.append(chosenPad)
            
            
        self.add(self.player, z=1000)
        

    def nearestPad(self, fromPoint, toPoint, maxRange, exclPad):
        shortestDistance = 999999.0
        closestPad = None
        
        for child in self.get_children():
            if child.btype == "pad" and child != exclPad and child.disabled == False and child.spinning == False:
                padPoint = eu.Point2(child.position[0], child.position[1])
                
                # check angles to make sure it's ahead of us
                targetDirection = (toPoint - fromPoint).normalize()
                padDirection = (padPoint - fromPoint).normalize()
                if targetDirection.angle(padDirection) < math.radians(40):

                    distance = toPoint.distance(padPoint)
                
                    if distance < shortestDistance and distance < maxRange:
                        shortestDistance = distance
                        closestPad = child
                    
        return closestPad
               
    def startDisablePad(self, pad):
        pad.disabled = True
        
        
    def startPadJitter(self, pad):
        def randomJitter():
            maxJitter = 2
            maxJitterDoubled = 2 * maxJitter
        
            return (random.randint(0, maxJitterDoubled) - maxJitter, random.randint(0, maxJitterDoubled) - maxJitter)
            
        if self.player.currentPad == pad:
            jitterTime = 0.05
        
            move1 = ac.MoveBy(randomJitter(), jitterTime)
            move2 = ac.MoveBy(randomJitter(), jitterTime)
            move3 = ac.MoveBy(randomJitter(), jitterTime)
            move4 = ac.MoveBy(randomJitter(), jitterTime)
        
            pad.do((move1 + ac.Reverse(move1) + move2 + ac.Reverse(move2) + move3 + ac.Reverse(move3) + move4 + ac.Reverse(move4)) * 3)
            pad.do(ac.Delay(1) + ac.CallFuncS(self.endDisablePad))
        
        
    def endDisablePad(self, pad):
        pad.disabled = True
        pad.do(ac.ScaleTo(0, 1))
        
        if self.player.currentPad == pad and not self.player.invincible:
            
            self.player.currentPad = None
            self.player.disabled = True
            
            self.player.do(ac.ScaleTo(0, 1) + ac.CallFunc(self.level_lost))
            
        
    def enablePad(self, pad):
        pad.disabled = False
        
    def stopPadSpinning(self, pad):
        pad.spinning = False
        
    def showMessageOnPad(self, pad):
        self.lastCompliment = random.choice(self.compliments)
        self.compliments.remove(self.lastCompliment)
        
        label = cocos.text.Label(self.lastCompliment,
                                font_size=20,
                                font_name=consts['view']['font_name'],
                                anchor_y='center',
                                anchor_x='center',
                                width=600,
                                multiline=False,
                                align="center")
        label.position = (pad.position[0] + (random.randint(0, 140) - 70), pad.position[1] + (random.randint(0, 140) - 70))
        label.btype = "label"

        self.fn_show_label(label)
        label.do(ac.Show() + ac.ScaleTo(4, 2) | ac.FadeOut(2))
        
    def showMessageInBackground(self, msg):
        w, h = director.get_window_size()

        label = cocos.text.Label(self.lastCompliment,
                                font_size=50,
                                font_name=consts['view']['font_name'],
                                anchor_y='center',
                                anchor_x='center',
                                width=self.width,
                                multiline=False,
                                align="center")
        label.position = (w * 0.5, (h - ((h / 6) * self.backgroundLabelCount)) - 30)
        label.btype = "label"
        
        label.do(ac.Show() + ac.FadeIn(2))
        self.add(label)
        
        self.backgroundLabelCount += 1

    def updatePlayerFlyingWin(self, dt):
        buttons = self.buttons
        ma = buttons['right'] - buttons['left']
        if ma != 0:
            self.player.rotation += ma * dt * self.angular_velocity
            a = math.radians(self.player.rotation)
            self.impulse_dir = eu.Vector2(math.sin(a), math.cos(a))

        newVel = self.player.vel
        mv = buttons['up']
        if mv != 0:
            newVel += dt * mv * self.accel * self.impulse_dir
            nv = newVel.magnitude()
            if nv > self.topSpeed:
                newVel *= self.topSpeed / nv
                
        ppos = self.player.cshape.center
        newPos = ppos
        r = self.player.cshape.r
        while dt > 1.e-6:
            newPos = ppos + dt * newVel
            consumed_dt = dt
            # what about screen boundaries ? if colision bounce
            if newPos.x < r:
                consumed_dt = (r - ppos.x) / newVel.x
                newPos = ppos + consumed_dt * newVel
                newVel = -reflection_y(newVel)
            if newPos.x > (self.width - r):
                consumed_dt = (self.width - r - ppos.x) / newVel.x
                newPos = ppos + consumed_dt * newVel
                newVel = -reflection_y(newVel)
            if newPos.y < r:
                consumed_dt = (r - ppos.y) / newVel.y
                newPos = ppos + consumed_dt * newVel
                newVel = reflection_y(newVel)
            if newPos.y > (self.height - r):
                consumed_dt = (self.height - r - ppos.y) / newVel.y
                newPos = ppos + consumed_dt * newVel
                newVel = reflection_y(newVel)
            dt -= consumed_dt

        self.player.vel = newVel
        self.player.update_center(newPos)        
        
    def updateRadarSwipe(self, dt):
        self.swipeDecay -= dt
        if self.swipeDecay < 0.0:
            
            self.swipeDecay = 0.2
            
            self.swipeAngle -= 3.0
            if self.swipeAngle < 0:
                self.swipeAngle += 360
                self.swipePads = [x for x in self.get_children() if x.btype == "pad" and x.disabled == False]
                
            padsToRemove = []
            w, h = director.get_window_size()
            origin = eu.Point2(0.5 * w, 0.5 * h)
            rightOfOrigin = eu.Point2(origin.x + 600.0, origin.y)
            # startVector = (rightOfOrigin - origin).normalize()
            # startVector = startVector.rotate(math.radians(self.swipeAngle))
            endPoint = self.rotatePoint(rightOfOrigin, origin, self.swipeAngle)
            
            #print("testing pads", len(self.swipePads), "at angle", self.swipeAngle)
            swipeLine = eu.LineSegment2(origin, endPoint)
            
            # line = draw.Line((swipeLine.p1.x, swipeLine.p1.y), (swipeLine.p2.x, swipeLine.p2.y), (255, 255, 255, 255))
            # line.btype = "line"
            # self.add(line)
            
            for pad in self.swipePads:
                circle = eu.Circle(eu.Point2(pad.position[0], pad.position[1]), 8.0)
                if swipeLine.intersect(circle) != None and not pad.specialTriggered:
                    padsToRemove.append(pad)
                    pad.spinning = True
                    pad.do(ac.FadeOut(0.2) + ac.Delay(1.5) + ac.FadeIn(0.2) + ac.CallFuncS(self.stopPadSpinning))
            
            for pad in padsToRemove:
                self.swipePads.remove(pad)
                    
            


    def update(self, dt):
        # if not playing dont update model
        if self.win_status != 'undecided':
            if self.win_status == 'complete':
                self.updatePlayerFlyingWin(dt)
            return

        self.updateRadarSwipe(dt)

        # check distances to the special pads
        if self.specialPadMessageDecay > 0.0:
            self.specialPadMessageDecay -= dt
        else:
            for p in self.specialPads:
                if p.specialTriggered == False:
                    padPoint = eu.Point2(p.position[0], p.position[1])
                    playerPos = eu.Point2(self.player.position[0], self.player.position[1])

                    if padPoint != playerPos:           # this is daft but euclid crashes when calling distance on two points that are the same
                        distance = playerPos.distance(padPoint)
            
                        if distance < 80:
                            self.showMessageOnPad(p)
                            self.specialPadMessageDecay = 2
                            break


        # update player
            
        buttons = self.buttons
        ma = buttons['right'] - buttons['left']
        if ma != 0:
            self.player.rotation += ma * dt * self.angular_velocity
            a = math.radians(self.player.rotation)
            self.impulse_dir = eu.Vector2(math.sin(a), math.cos(a))

        newVel = self.player.vel
        mv = buttons['up']
        
        if self.player.moveDecay > -1.0:
            self.player.moveDecay -= dt
            
            # newVel += dt * self.accel * self.player.moveDecay * 0.5 * self.impulse_dir
  
        if mv == 0 and self.player.moveDecay < 0.0:
            self.upButtonReleased = True         
        
        if mv != 0 and (self.upButtonReleased or self.player.moveDecay < -0.2) and not self.player.disabled:
            self.upButtonReleased = False
            
            moveDuration = 0.25
            self.player.moveDecay = moveDuration
            
            #print("cshape.center: ", self.player.cshape.center)
            playerPos = eu.Point2(self.player.position[0], self.player.position[1])
            futurePos = playerPos + (self.impulse_dir * 30)
            
            nearestPad = self.nearestPad(playerPos, futurePos, 30, self.player.currentPad)
            if nearestPad != None:
                futurePos = eu.Point2(nearestPad.position[0], nearestPad.position[1])
                self.player.currentPad = nearestPad

                if nearestPad.special:
                    if not nearestPad.specialTriggered:
                        nearestPad.color = Actor.palette['special']
                        nearestPad.specialTriggered = True
                
                        self.showMessageInBackground(self.lastCompliment)
                        
                        padsUntriggered = [p for p in self.specialPads if p.specialTriggered == False]
                        if len(padsUntriggered) == 0:
                            self.do(ac.Delay(3) + ac.CallFunc(self.level_complete))
                            #self.level_complete()
                    
                else:                
                    nearestPad.do(ac.Delay(0.8) + ac.CallFuncS(self.startPadJitter)) #+ ac.Delay(1) + ac.CallFuncS(self.endDisablePad))
                    # action = ac.CallFuncS(self.startDisablePad) + ac.FadeOut(2) + ac.CallFuncS(self.endDisablePad) + ac.RandomDelay(10, 25) + ac.CallFuncS(self.enablePad) + ac.FadeIn(1)
                    # nearestPad.do(action)
                    
                move = ac.MoveTo((futurePos.x, futurePos.y), duration = moveDuration)
                self.player.do(move)
            else:
                self.player.currentPad = None
                self.player.disabled = True
                
                move = ac.MoveTo((futurePos.x, futurePos.y), duration = moveDuration)
                self.player.do(move | ac.ScaleTo(0, 1) + ac.CallFunc(self.level_lost))

        
        playerWorldPos = view_to_world(self.player.position[0], self.player.position[1])
        self.player.cshape.center = eu.Vector2(playerWorldPos[0], playerWorldPos[1])


    def open_gate(self):
        self.gate.color = Actor.palette['gate']

    def on_key_press(self, k, m):
        binds = self.bindings
        if k in binds:
            self.buttons[binds[k]] = 1
            return True
        return False

    def on_key_release(self, k, m):
        binds = self.bindings
        if k in binds:
            self.buttons[binds[k]] = 0
            return True
        return False


def main():
    # make window
    director.init(**consts['window'])
    #pyglet.font.add_directory('.') # adjust as necessary if font included
    scene = cocos.scene.Scene()
    palette = consts['view']['palette']
    Actor.palette = palette
    r, g, b = palette['bg']
    scene.add(cocos.layer.ColorLayer(r, g, b, 255), z=-1)
    message_layer = MessageLayer()
    scene.add(message_layer, z=1)
    playview = Worldview(fn_show_message=message_layer.show_message, fn_show_label=message_layer.show_label)
    scene.add(playview, z=0)
    director.run(scene)

main()
