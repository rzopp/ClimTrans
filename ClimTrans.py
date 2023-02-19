import argparse
import json
import numpy as np
import pandas as pd
from math import radians, sin, cos, asin, acos, atan, sqrt, exp, isnan
from great_circle_calculator.great_circle_calculator import distance_between_points, bearing_at_p1, bearing_at_p2, midpoint
# from sqlalchemy import create_engine
import psycopg2
#import googlemaps
import requests
import xmltodict
import dbdef
import aero

gci = 1.03  # default great circle index
paxmass = 95    # average passenger mass
baseUrlBing = 'http://dev.virtualearth.net/REST/V1'
endpointRoutes = '\Routes'
endpointLocations = '\Locations'
Bingkey = 'AoH17SfBDXWAJKeGwekk3u-5MiquBNmv9iPjSAhCYRlgT95E9VKpWoPcyXu6EN1Y'
baseUrlCO2signal = 'https://api.co2signal.com/v1'
endpointCO2latest = '/latest'
CO2token = 'YP9SsIrYlJIcacNY0N9sJUiwCDDoXqMj'
gwpfact = {'gasoline':2.3, 'diesel':2.52, 'kerosene':3.15, 'electric':0.5}

def str2hours(str):
    hours = str.split(':')[0]
    minutes = str.split(':')[1]
    return float(hours)+float(minutes)/60

def hours2str(h):
    return '{:02d}:{:02d}'.format(int(h),int((h-int(h))*60))

def greatcircle(geo1, geo2): # dist in km
    p1 = [geo1[1],geo1[0]]  # swap axes
    p2 = [geo2[1],geo2[0]]
    dist = distance_between_points(p1, p2)/1000
    pm = midpoint(p1,p2)
    trk = bearing_at_p2(p1, pm)
    return dist, trk

def getlocation(str):   # creates a 0-distance driving routing from point A to point A to get the coordinates of point A
    # first check if it is an airport:
    sql = "select iata, icao, name, lat, lng from airports where iata = '{}' order by 1".format(str)
    cur.execute(sql)
    row = cur.fetchone()
    if row != None:     # airport found
        return row[3],row[4]
    else:
        rq = '/Driving?wp.0={}&wp.1={}&timeType=Departure&dateTime={}&output=xml&ra=routePath,transitStops&key={}'.format(str,str,'12:00',Bingkey)
        x = requests.get(baseUrlBing + endpointRoutes + rq)
        if x.ok:
            dict = xmltodict.parse(x.content.decode())
            pt0 = dict['Response']['ResourceSets']['ResourceSet']['Resources']['Route']['RouteLeg']['ActualStart']
            return [float(pt0['Latitude']),float(pt0['Longitude'])]
        else:
            return [0,0]

def getCO2signal(geo):
    rq = '?lat={}&lon={}'.format(geo[0],geo[1])
    hd = {"auth-token": CO2token}
    x = requests.get(baseUrlCO2signal + endpointCO2latest + rq, headers = hd)
    if x.ok:
        data = json.loads(x.content)
        countryCode = data['countryCode']
        carbonIntensity = data['data']['carbonIntensity']/1000
    else:
        countryCode = '??'
        carbonIntensity = 0.5
    return countryCode, carbonIntensity      # ISA 2-letter country code, kgCO2/kWh

def closestairport(geo):
    sql = 'select iata, icao, lat, lng, (abs({}-lat))^2+(abs({}-lng)*cos(radians(lat)))^2 as dlat from airports group by iata, icao, lat, lng order by dlat asc limit 1'.format(geo[0], geo[1])
    cur.execute(sql)
    row = cur.fetchone()
    if row != None:
        closestapt = row[0]
        closestgeo = [row[2], row[3]]
        mindist = sqrt(row[4])
    return closestapt, closestgeo, mindist

def getwc(tas, trk):
    wu = 45
    wv = 0
    return cos(radians(trk-90))*wu

def load_aircraft():
    global aircraft
    sql = 'SELECT subtype, paxcap, cargocap, dom, mzfm, mtom, avrsv, avtas, maxalt, breguet, avtaxifuel FROM public.aircraft order by 1;'
    aircraft = pd.read_sql_query(sql, conn, index_col = 'subtype')

    return

class Vehicle:
    def __init__(self, ident):
        self.ident = ident
        self.fueltype = 'gasoline'
        self.speccons = 0.0
        self.paxcap = 4
        self.wttfact = 0.2  # well-to-tank CO2 overhead
        self.taxit = 0

    def getparam(self, param, default):
        if isnan(param):
            return default
        else:
            return param

class Trainobject(Vehicle):
    def __init__(self, traintyp):
        Vehicle.__init__(self, traintyp)
        self.fueltype = 'electric'
        self.wttfact = 0.2  # well-to-tank CO2 overhead
        self.speccons = 2000    # kWh/100km
        self.paxcap = 550

class Busobject(Vehicle):
    def __init__(self, bustyp):
        Vehicle.__init__(self, bustyp)
        self.fueltype = 'diesel'
        self.wttfact = 0.2  # well-to-tank CO2 overhead
        self.speccons = 25.0    # lt/100km
        self.paxcap = 55

class Carobject(Vehicle):
    def __init__(self, cartyp):
        Vehicle.__init__(self, cartyp)
        self.fueltype = 'gasoline'
        self.wttfact = 0.7  # well-to-tank CO2 overhead
        self.speccons = 6.0     # lt/100km
        self.paxcap = 4

class Aircraftobject(Vehicle):
    def __init__(self, actyp):
        Vehicle.__init__(self, actyp)
        self.fueltype = 'kerosene'
        self.wttfact = 0.7  # well-to-tank CO2 overhead
        ac = aircraft.loc[actyp].values
        self.paxcap = self.getparam(ac[0], 100)
        self.dom = self.getparam(ac[2], 20000)
        self.cargocap = self.getparam(ac[1], self.dom * 0.01)
        self.avres = self.getparam(ac[5], self.dom * 0.03)
        self.avtas = self.getparam(ac[6], 800)
        self.breguet = self.getparam(ac[8], 5.6E-8)
        self.taxif = self.getparam(ac[9], 200)
        self.taxit = 15/60  # taxi time in hours
        self.pfact = 1.03

    def gettripf(self, ldm, esad):
        return ldm * (exp(esad * 1000 * self.breguet) - 1) * self.pfact + self.taxif

class Routeobject:
    def __init__(self, wp0, wp1, deptime, pax):
        self.deptime = deptime
        self.vehicle = Vehicle('')
        self.pax = pax
        self.totaldist = 0
        self.totaltime = 0
        self.totalfuel = 0
        self.rfi = 1.0
        self.loadfact = 0.3
        self.infrafact = 0.001 # kgCO2/pkm
        self.geo0 = wp0
        self.geo1 = wp1
        self.countryCode, self.carbonIntensity = getCO2signal(self.geo0)    # electric carbon data at start point

    def get_bingroute(self, type):
        rq = '/{}?wp.0={},{}&wp.1={},{}&timeType=Departure&dateTime={}&output=xml&ra=routePath,transitStops&key={}'.format(type, self.geo0[0], self.geo0[1], self.geo1[0], self.geo1[1], self.deptime,Bingkey)
        x = requests.get(baseUrlBing + endpointRoutes + rq)
        if x.ok:
            dict = xmltodict.parse(x.content.decode())
            self.route = dict['Response']['ResourceSets']['ResourceSet']['Resources']['Route']
            self.totaldist = float(self.route['TravelDistance'])
            self.totaltime = float(self.route['TravelDuration']) / 3600.0
            self.totalfuel = self.totaldist*self.vehicle.speccons/100

    def get_gwpwtt(self):   # CO2 from well to tank
        return self.totalfuel*self.vehicle.wttfact

    def get_gwp(self):
        if self.vehicle.fueltype == 'electric':
            return self.totalfuel * self.carbonIntensity
        else:
            return self.totalfuel * gwpfact[self.vehicle.fueltype]

    def get_gwppax(self):
        return self.get_gwp() / self.pax

    def get_gwpe(self):
        return self.get_gwp()+self.get_gwpwtt()

    def get_gwpepax(self):
        return self.get_gwpe() / self.pax + self.totaldist*self.infrafact


class RailRoute(Routeobject):
    def __init__(self, wp0, wp1, deptime, pax):
        Routeobject.__init__(self, wp0, wp1, deptime, pax)
        self.rttype = 'Rail'
        self.loadfact = 0.45
        self.vehicle = Trainobject('ICE')
        self.pax = self.vehicle.paxcap*self.loadfact
        self.infrafact = 0.04    # kgCO2/pkm
        self.get_bingroute('Transit')
        self.totaltime += 0.25  # arrive at first train station 15 minutes befure departure

class DrivingRoute(Routeobject):
    def __init__(self, wp0, wp1, deptime, pax):
        Routeobject.__init__(self, wp0, wp1, deptime, pax)
        self.rttype = 'Car'
        self.vehicle = Carobject('VW Golf')
        if pax == 0:
            self.loadfact = 0.3
            self.pax = self.vehicle.paxcap * self.loadfact
        else:
            self.loadfact = pax / self.vehicle.paxcap
            self.pax = pax
        self.infrafact = 0.03    # kgCO2/pkm
        self.get_bingroute('Driving')

class FlightRoute(Routeobject):
    def __init__(self, wp0, wp1, deptime, pax, depapt, dstapt):
        Routeobject.__init__(self, wp0, wp1, deptime, pax)
        self.loadfact = 0.85
        self.aptinfra = 1.5     # airport infrastrucuture kgCO2/pax
        self.rttype = 'Flight'
        self.fueltype = 'kerosene'
        self.infrafact = 0.00    # kgCO2/pkm

        self.gcdist, self.trk = greatcircle(depapt[1], dstapt[1])
        if self.gcdist <= 300:
            actyp =  'DHC-8-400'
        elif self.gcdist <= 1200:
            actyp =  'E190'
        elif self.gcdist <= 3000:
            actyp =  'A320'
        elif self.gcdist <= 7000:
            actyp =  'B763'
        else:
            actyp =  'A359'

        self.vehicle = Aircraftobject(actyp)

        sid = 20  # default departure maneuvering distance
        star = 30  # default arrival maneuvering distance
        self.pax = self.vehicle.paxcap * self.loadfact
        ldm = self.vehicle.dom + self.vehicle.cargocap + self.pax * paxmass + self.vehicle.avres
        wc = getwc(self.vehicle.avtas, self.trk)
        self.esad = self.gcdist * gci * self.vehicle.avtas / (self.vehicle.avtas + wc) + sid + star
        self.totaldist = self.esad
        self.totalfuel = self.vehicle.gettripf(ldm, self.esad)
        self.triptime = self.totaldist/(self.vehicle.avtas)+self.vehicle.taxit

        self.Origtransit = DrivingRoute(wp0,depapt[1], deptime, pax)
        self.takeoff = str2hours(deptime) + self.Origtransit.totaltime + 1.5
        self.landing = self.takeoff+self.totaltime
        self.Desttransit = DrivingRoute(dstapt[1], wp1, hours2str(self.landing), pax)
        self.totaldist += self.Origtransit.totaldist + self.Desttransit.totaldist
        self.totaltime = self.triptime + self.Origtransit.totaltime + 1.5 + 0.5 + self.Desttransit.totaltime

        # radiative forciong index for non-co2 effects
        if self.gcdist < 600:  # no rfi for short-haul flights
            self.rfi = 1.0
        elif self.takeoff >= 5 and self.takeoff <= 16 and self.landing >= 5 and self.landing <= 18:
            self.rfi = 1.1  # low rfi during daytime, mostly NOx
        else:
            self.rfi = 2.0

    def get_gwpe(self):
        return self.get_gwp()*self.rfi+self.get_gwpwtt()+self.Origtransit.get_gwpe()+self.Desttransit.get_gwpe()

    def get_gwpepax(self):
        return (self.get_gwp()*self.rfi+self.get_gwpwtt())/self.pax+self.Origtransit.get_gwpepax()+self.Desttransit.get_gwpepax() + 2*self.aptinfra

if __name__ == '__main__':
    # 2021-12-05 09:00 2 "Wien, Mariahilfer Strasse" "Nice, France"
    parser = argparse.ArgumentParser(description='calclation parameters')
    parser.add_argument('date')
    parser.add_argument('time')
    parser.add_argument('pax')
    parser.add_argument('origin')
    parser.add_argument('destination')
    args = parser.parse_args()

    conn = psycopg2.connect(host=dbdef.dbs['fkylab']['host'], database=dbdef.dbs['fkylab']['database'], user=dbdef.dbs['fkylab']['user'], password=dbdef.dbs['fkylab']['password'])

    load_aircraft()
    cur = conn.cursor()

    depdate = args.date
    deptime = args.time
    pax = float(args.pax)
    origgeo = getlocation(args.origin)
    destgeo = getlocation(args.destination)
    depapt = closestairport(origgeo)
    dstapt = closestairport(destgeo)

    conn.close()

    country, co2 = getCO2signal(origgeo)

    itineraries =[]
    itineraries.append(FlightRoute(origgeo, destgeo, deptime, pax, depapt, dstapt))
    itineraries.append(DrivingRoute(origgeo, destgeo, deptime, pax))
    itineraries.append(RailRoute(origgeo, destgeo, deptime, pax))

    actyp = itineraries[0].vehicle.ident
    print('Climate footprint\nfrom {} to {}'.format(args.origin, args.destination))
    print('departing {} {} with {:.1f} pax:'.format(depdate, deptime, pax))
    print('Mode     Load fact  Dist       Time      CO2        GWPe ')
    print('                     km         h      kg/pax    kgCO2/pax')
    print('------------------------------------------------------------------')
    for itinerary in itineraries:
        if itinerary.totaldist == 0:
            print('{} calculation failed'.format(itinerary.rttype))
        else:
            print('{:7}   {:4.0f}%   {:8.1f}    {:5}  {:8.1f}   {:8.1f}'.format(itinerary.rttype, itinerary.loadfact*100, itinerary.totaldist, hours2str(itinerary.totaltime), itinerary.get_gwppax(), itinerary.get_gwpepax()))
    print('\nFlight details:\n{} {}-{} GCD {:0.0f}km, ESAD {:0.0f}km Fuel {:0.0f}kg, Time {}h'.format(actyp, depapt[0], dstapt[0], itineraries[0].gcdist, itineraries[0].esad, itineraries[0].totalfuel, hours2str(itineraries[0].triptime)))
    print('{} - {}: {:0.1f}km {}, {} - {}: {:0.1f}km {}'.format(args.origin, depapt[0], itineraries[0].Origtransit.totaldist, hours2str(itineraries[0].Origtransit.totaltime), dstapt[0], args.destination, itineraries[0].Desttransit.totaldist, hours2str(itineraries[0].Desttransit.totaltime)))
    # print('Rail speccons {:0.4f} kWh/pkm'.format(itinerary.totalfuel/itinerary.totaldist/itinerary.pax))


