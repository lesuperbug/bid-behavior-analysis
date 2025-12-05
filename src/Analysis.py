#%% Preliminaries

import os
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.anova import anova_lm
from linearmodels import PanelOLS
import matplotlib.pyplot as plt
import requests                                # HTTP requests
import scipy.stats as stats
import matplotlib.pyplot as plt

# Working Directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

#%% Functions

def retrieve_allowed_assets():
    '''
    This function will prepare the allowed asset list based on fuel types
    '''

    filename = r'CSD Generation (Hourly) - 2020-01 to 2020-06.csv'
    fuel_ref_df = pd.read_csv(filename)
    fuel_ref_df = fuel_ref_df[~fuel_ref_df['Asset Short Name'].duplicated()].reset_index()
    fuel_ref_df = fuel_ref_df[~fuel_ref_df['Fuel Type'].isin(['WIND', 'SOLAR'])].reset_index()
    fuel_ref_df = fuel_ref_df[['Asset Short Name', 'Fuel Type']]
    fuel_ref_df.rename(columns={'Asset Short Name':'Allowed Assets'}, inplace=True)
    return fuel_ref_df

def retrieve_nd_gen():
    '''
    This function retrievs non-dispatchable generation data as Datarame
    '''

    filename = r'Wind and Solar Generation History.xlsx'
    nd_gen_df = pd.read_excel(filename)
    nd_gen_df.rename(columns={'Timestamp (UTC)':'DateTime'}, inplace=True)
    nd_gen_df['DateTime'] = pd.to_datetime(nd_gen_df['DateTime'])
    nd_gen_df.drop(columns='Timestamp (MT)', inplace=True)
    nd_gen_df['DateTime'] -= pd.Timedelta(hours=7)
    nd_gen_df = nd_gen_df[nd_gen_df['DateTime'] >= pd.Timestamp(year=2020, month=1, day=1)]
    nd_gen_df.reset_index(drop=True, inplace=True)
    nd_gen_df['Non-Dispatchable Gen.'] = nd_gen_df['Wind'] + nd_gen_df['Solar']
    return nd_gen_df

def make_aeso_api_call(date):
    '''
    This function makes a single API call to aeso API, requesting merit order data for the date given as
    the date paramater. It returns the data portion of the APU response.
    '''

    # Parameters for API call
    key = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0a3hoajQiLCJpYXQiOjE2ODY0NDM3MzF9.VQyw1jcoYmGO4iQscQalEnpYinMMUAW4qGHGl1Mqxms'
    base_url = 'https://api.aeso.ca/report/v1/meritOrder/energy'

    date = pd.Timestamp(date)
    params = {'startDate': date.strftime('%Y-%m-%d')}
    headers = {'accept': 'application/json', 'X-API-Key': key}

    try:
        # Retrieve API repsonse
        response = requests.get(base_url, params=params, headers=headers)

        # Check if the request was successful (status code 200)
        if response.status_code == 200:
            # Load the JSON data into a Pandas DataFrame
            data = response.json()
            day_data = data['return']['data']
        else:
            print(f"API call failed with status code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"An error occurred while making the API call: {e}")

    return day_data

def unpack_assets(date_time, bid_list):
    '''
    Note: This function unpacks all 24 hours' worth of bids from the argument passed as bid_list. Therefore,
    it needs to be called more than one if trying to retrieve more than one day's worth of data.
    '''

    # Declaring variables
    collector_df = pd.DataFrame()

    # Repackage the bid_data from the dictionaries in the list
    for bid in bid_list:
        block_size = bid['to_MW'] - bid['from_MW']
        bid_data = pd.DataFrame({'DateTime':[date_time],
                                'Owner':[bid['offer_control']],
                                'Plant':[bid['asset_ID']],
                                'Block Price':[float(bid['block_price'])],
                                'Block Size':[float(block_size)],
                                'Import/Export':[str(bid['import_or_export'])]})

        # Append the repackaged bid data to the dataframe
        collector_df = pd.concat([collector_df, bid_data], ignore_index=True)
    
    return collector_df

def aggregate_api_returns():
    '''
    This fuction uses the above helper functions to retrieve the data for the year 2020
    '''

    # Declaring relevant variables
    current_date = pd.Timestamp('2020-01-01')
    merit_df = pd.DataFrame()

    # Build dataframe of objects reurned by API calls
    while current_date <= pd.Timestamp('2020-12-31'):
        temp_df = pd.DataFrame(make_aeso_api_call(current_date))
        merit_df = pd.concat([merit_df, temp_df], ignore_index=True)
        print(current_date)
        merit_df.drop(columns=['begin_dateTime_mpt'], inplace=True)
        current_date += pd.DateOffset(days=1)

    merit_df.rename(columns={'begin_dateTime_utc':'DateTime'}, inplace=True)
    merit_df['DateTime'] = pd.to_datetime(merit_df['DateTime'])
    merit_df['DateTime'] -= pd.Timedelta(hours=7)
    return merit_df

def build_unclean_panel(agg_api):
    '''
    This function unpacks all the objects that remain in the 'energy_blocks' column of the aggregateed df
    '''

    # Declaring relevant variables
    panel_df = pd.DataFrame()

    # Unpack assets
    for obs in range(len(agg_api)):
        temp_df = unpack_assets(agg_api.iloc[obs,0], agg_api.iloc[obs,1])
        panel_df = pd.concat([panel_df, temp_df], ignore_index=True)
        print(obs)

    return panel_df

def clean_panel(daily_data):

    # Declaring relevant variables
    company_keys_path = r'company name reference.csv'
    company_keys = pd.read_csv(company_keys_path)
    asset_keys = list(retrieve_allowed_assets()['Allowed Assets'])

    # Calcuate weighted bid by plant and company
    daily_data['Weighted Bid'] = daily_data['Block Price'] * daily_data['Block Size']
    plant_blocks_df = daily_data.groupby(['DateTime', 'Plant']).agg({'Weighted Bid': 'sum', 'Block Size': 'sum'}).reset_index()
    company_blocks_df = daily_data.groupby(['DateTime', 'Owner']).agg({'Weighted Bid': 'sum', 'Block Size': 'sum'}).reset_index()
    merge_one = daily_data.merge(plant_blocks_df, on=['DateTime', 'Plant'], how='left', suffixes=('',' - Plant'))
    merge_two = merge_one.merge(company_blocks_df, on=['DateTime', 'Owner'], how='left', suffixes=('',' - Owner'))

    # Remove / Edit / Combine observations that will not be used
    merge_two = merge_two[merge_two['Owner'].isin(list(company_keys['Offer Controller']))]
    merge_two = merge_two[merge_two['Plant'].isin(asset_keys)]
    merge_two = merge_two[merge_two['Import/Export'] == '']
    name_mapping = dict(zip(company_keys['Offer Controller'], company_keys['Name']))
    merge_two['Owner'].replace(name_mapping, inplace=True)

    # Calculate
    merge_two['VWAB - Plant'] = merge_two['Weighted Bid - Plant'] / merge_two['Block Size - Plant']
    merge_two['VWAB - Owner'] = merge_two['Weighted Bid - Owner'] / merge_two['Block Size - Owner']

    # Drop columns / rows
    merge_two.drop(columns=['Import/Export', 'Weighted Bid', 'Block Size', 'Block Price'], inplace=True)

    # Return the relevant values
    return merge_two

def build_analysis_panel(pre_nd_panel):
    '''
    This function will add non-dispatchable generation data to the main panel of data
    '''

    # Get data
    nd_gen_df = retrieve_nd_gen()

    # Combine all data
    analysis_frame = pre_nd_panel.merge(nd_gen_df, on='DateTime', how='left')

    # Return data for analysis
    return analysis_frame

def log_transform_vars(panel, constant=1):
    '''
    This function simply adds a constant and log transforms the important variables
    '''

    panel['ln_pool_price'] = np.log(panel['Pool Price']+constant)
    panel['ln_nd_gen'] = np.log(panel['Non-Dispatchable Gen.']+constant)
    panel['ln_AIL'] = np.log(panel['AIL']+constant)
    panel['ln_vwab_owner'] = np.log(panel['VWAB - Owner']+constant)
    panel['ln_vwab_plant'] = np.log(panel['VWAB - Plant']+constant)
    panel['ln_pool_price'] = np.log(panel['Pool Price']+constant)
    panel['ln_solar'] = np.log(panel['Solar']+constant)
    panel['ln_wind'] = np.log(panel['Wind']+constant)
    return panel

#%% Get Data

def get_data():
    '''
    This funtion will do the final preparations of the data for analysis
    '''

    # Data processing
    merit_df = aggregate_api_returns()
    unclean_panel = build_unclean_panel(merit_df)
    pre_nd_panel = clean_panel(unclean_panel)
    analysis_panel = build_analysis_panel(pre_nd_panel)

    return analysis_panel

#%% Summary Stats

def get_sum_stats():

    sum_stats_plant = analysis_panel.groupby('Plant')
    sum_stats_plant['Block Size - Plant'].describe().to_excel('Plant - Block Size.xlsx')
    sum_stats_plant['VWAB - Plant'].describe().to_excel('Plant - VWAB.xlsx')

    sum_stats_owner = analysis_panel.groupby('Owner')
    sum_stats_owner['Block Size - Owner'].describe().to_excel('Owner - Block Size.xlsx')
    sum_stats_owner['VWAB - Owner'].describe().to_excel('Owner - VWAB.xlsx')

    return

#%% Regressions

def run_regression(panel, regressand, entity):
    '''
    This function does the relevant work to rin the regression (add constants, etc.)
    '''
    
    # Basics
    panel = panel.copy()    
    panel['Month'] = panel['DateTime'].dt.month
    panel['Month'] = panel['Month'].astype('category')
    panel['Hour'] = panel['DateTime'].dt.hour
    panel['Month.1'] = (panel['DateTime'].dt.month == 1).astype(int)

    # Setting the index, regressors, and regressand
    panel.set_index([entity, 'Hour'], inplace=True)
    y = panel[regressand]
    X = panel[['ln_solar', 'AIL', 'Month.1', 'Month']]

    # Regression and results
    regression = PanelOLS(y, X, entity_effects=True, time_effects=True, drop_absorbed=True)
    model = regression.fit(cov_type="clustered", cluster_entity=True, cluster_time=True)
    print(model.summary)

    return model

# %%

def main():
    '''
    This is the main function that will run the analysis
    '''

    # Get data
    analysis_panel = get_data()
    analysis_panel = log_transform_vars(analysis_panel)

    # Run regressions
    plant_model = run_regression(analysis_panel, 'ln_vwab_plant', 'Plant')
    owner_model = run_regression(analysis_panel, 'ln_vwab_owner', 'Owner')

    return plant_model, owner_model

if __name__ == "__main__":
    main()
    # Note: This will only run if this script is executed directly, and not if it is imported as a module.

#%% End of File