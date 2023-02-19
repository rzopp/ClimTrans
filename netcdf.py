import numpy as np
import xarray as xr

if __name__ == '__main__':
    # open single hour
    filename = 'data/*.nc'
    ds = xr.open_mfdataset(filename)
    da = ds['ef_per_m']
    print('hPa,  Lat,    Lng,    EF (J/m),  EF (MJ/NM), GWP (TCO2/NM)')
    for level in da.level:
        for lat in np.arange(50, 70, 1):
            for long in np.arange(-20, 30, 1):
                ef = da.sel(latitude=lat, longitude=long, level=level, time='2022-01-10T10:00:00')
                if  ef != 0:
                    efx = float(ef)*1.852/1E+9  # convert J/m to MJ/NM
                    print('{:3.0f}, {:6.2f}, {:7.2f}, {:10.2E}, {:10.2f}, {:10.2f}'.format(float(level),lat,long,float(ef), round(efx,1), efx/40.5))


    print('done')