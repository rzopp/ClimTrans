import math

# basic ISA standard atmosphere constants:
g0 = 9.80665  	# m/s
P0 = 101325		# Pa
dTC = 273.15	# Celsius difference
T0 = dTC + 15.0		# °K
rho0 = 1.225	# kg/m3
tg0	 = 0.0065	# °K/m
htp  = 11000	# m
k    = 1.4
lbda = 1.49627825E-06

#derived constants:
R = P0/rho0/T0
a0 = (k*R*T0)**0.5
ex1 = g0/R/tg0		# tropospheric pressure exponent
ex2 = 6342.657		# stratospheric pressure exponent

C0 = (k*R)**0.5
C1 = 0.7
C2 = (k-1)/k
C3 = 2*P0/rho0/C2
C4 = 1/C2
C5 = (k-1)/2
C6 = C0/lbda/R
C7 = C5
C8 = (k/rho0)**0.5
C9 = k*tg0*R/2/g0
C10 = tg0*(ex1-1)*C0**2/2/g0
C11 = 1-C10/C1
Ptp = P0*((T0-tg0*htp)/T0)**ex1		# pressure at tropopause
Deltatp = Ptp/P0                    # delta at tropopause

nm2m = 1852					# NM to m conversion
kt2ms = nm2m/3600			# kts to m/s conversion
ft2m = 0.3048				# ft to m conversion
fpm2mps = ft2m/60			# ft/min to m/s conversion
lbs2kg = 0.45359237			# pounds to kg conversion
lbf2dan = lbs2kg*g0/10   	# pound force to dekanewton conversion
usg2lt = 3.78541			# us gallons to litres
sm2m = 1609.344				# statute miles to meters
mph2mps = sm2m/3600			# miles per hour to m/s

c2f = 1.8				# delta celsius to delta fahrenheit conversion

# note that all aero functions use SI units (K, m, s, kg) even for altitude!

def isaT(alt):		# alt in m, returns ISA temp in Kelvin
	return T0-min(htp, alt)*tg0
	
def C2K(celsius):
	return celsius+dTC
	
def K2C(kelvin):
	return kelvin-dTC

def theta(alt):		# alt in m, theta at ISA
	return 1-min(htp, alt)*tg0/T0

def delta(alt):		# alt in m
	if alt <= htp:
		return theta(alt)**ex1
	else:
		return Deltatp*math.exp((htp-alt)/ex2)

def altitude(delta):		# return alt in m from delta
	if delta < Ptp/P0:		# below tropopause
		return (1-delta**(1/ex1))*T0/tg0
	else:	
		return (htp-ex2*math.log(delta/Ptp*P0))
		
def cas2mach(cas, alt):	# cas in m/s, alt in m
	return (((((cas**2/C3 + 1)**C4 - 1)/delta(alt) + 1)**C2 - 1)/C5)**0.5

def mach2cas(mach, alt):	    # alt in m, cas result in m/s
	return (C3*((delta(alt)*((1+C5*mach**2)**C4-1)+1)**C2-1))**0.5

def tas2mach(tas, alt, disa):	# alt in m, tas in m/s
	return tas/(C0*(isaT(alt)+disa)**0.5)

def mach2tas(mach, alt, disa):	# tas in m/s
	return mach*C0*(isaT(alt)+disa)**0.5

def cas2tas(cas, alt, disa):	# alt in m, cas, tas in m/s
	return(mach2tas(cas2mach(cas, alt), alt, disa))
	
def tas2cas(tas, alt, disa):	# alt in m, cas, tas in m/s
	return(mach2cas(tas2mach(tas, alt, disa), alt))
	
def get_transition_delta(cas, mach):
	if mach > 0:
		return ((cas**2/C3+1)**C4-1)/((1+C5*mach**2)**C4-1)
	else:
		return 1.0
	
def get_transition_alt(cas, mach):
	return altitude(get_transition_delta(cas, mach))

def getphi(mach):
	m2 = mach**2
	c5m2 = C5*m2
	return ((1+c5m2)**3.5-1)/(C1*m2*(1+c5m2)**2.5)

def getfacc(alt,disa,mach,mode):    # alitude in m
	isat = isaT(alt)
	thetaisa = (isat+disa)/isat
	if mode == 'CAS':
		phi = getphi(mach)
	else:
		phi = 1
	if alt < htp:  # below tropopause
		if mode == 'CAS' or mode == 'EAS':
			facc = 1+mach**2*C1*(phi-C11/thetaisa)
		else:  # constant mach
			facc = 1-mach**2*C9/thetaisa
	else:		# at or above tropopause
		if mode == 'CAS' or mode == 'EAS':
			facc = 1-C1*getphi(mach)*mach**2
		else:
			facc = 1
	return facc

def getfnexc(alt,disa,mass,mach,rate,mode):    # alitude in m
	isat = isaT(alt)
	thetaisa = (isat+disa)/isat
	fnexc = rate*fpm2mps*thetaisa*mass*g0*getfacc(alt,disa,mach,mode)/mach2tas(mach,alt,disa)
	return fnexc

def getroc(alt, disa, mass, mach, fnexc, mode):    # point climb, alitude in m
	isat = isaT(alt)
	thetaisa = (isat+disa)/isat
	roc = fnexc*mach2tas(mach, alt, disa)/thetaisa/mass/g0/getfacc(alt,disa,mach,mode)
	return roc

def getrocacc(altm, dalt, disa, mass, tasm, dtas, fnexc):    # accelerated climb, alitude in m
	isat = isaT(altm)
	thetaisa = (isat+disa)/isat
	return fnexc/mass/(thetaisa*g0/tasm + dtas/dalt)

def getreqfn(altm, dalt, disa, mass, tasm, dtas, drag, reqrate):    # required thrust for accelerated climb, alitude in m
	isat = isaT(altm)
	thetaisa = (isat+disa)/isat
	if reqrate < 9E99:
		return reqrate*mass*(thetaisa*g0/tasm + dtas/dalt)+drag
	else:
		return 9E99

def straightmach(mach):
	if mach>0.0 and abs(round(mach,2) - mach) < 0.0000001:
		return True
	else:
		return False

