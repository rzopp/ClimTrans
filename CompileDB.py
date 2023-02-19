import aero
import argparse
import pandas as pd

if __name__ == '__main__':
#	parser = argparse.ArgumentParser(description = 'database connection parameters')
#	parser.add_argument('subtype')
#	parser.add_argument('version_nr')

#	args = parser.parse_args()
    cardb = pd.read_excel(r"O:\\Projects\Emission\\Climate Transparency\\Database\\Vehicles\\Test.xlsx", sheet_name="Sheet1")
    df = pd.DataFrame(cardb, columns= ['Brand','Model','Generation','Modification (Engine)','Power'])
    for i in range(0,len(df)):
        mfct = df['Brand'][i]
        model = df['Model'][i]
        name = df['Generation'][i]+' '+df['Modification (Engine)'][i]
        power = float(df['Power'][i].split('hp')[0])
       # speed = float(values[7].split()[0])
       # pax = int(values[11])
       # length = float(values[12].split()[0])/1000
       # width =  float(values[13].split()[0])/1000
       # height =  float(values[14].split()[0])/1000
       # fuel = values[30]
       # fcurb =  float(values[39].split()[0])
       # fceco =  float(values[40].split()[0])


