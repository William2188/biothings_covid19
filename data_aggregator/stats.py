import requests
import copy
import numpy as np
from datetime import timedelta
from datetime import datetime as dt
import pandas as pd
import logging

format_id = lambda x: x.replace(" ", "_").replace("&", "_")

def compute_doubling_rate(cases):
    x = np.arange(len(cases))
    y = np.log(cases)
    m,b = np.polyfit(x, y, 1)
    m = np.round(m,3)
    if m <= 0:
        return np.nan
    dr = np.log(2)/m
    dr = np.round(dr, 3)
    return dr if not np.isposinf(dr) and not np.isneginf(dr) else np.nan

def compute_days_since(cases, ncases, current_date):
    if cases[cases >= ncases].shape[0] == 0:
        return None
    first_gte_ncases = cases[cases >= ncases].index[0]
    if cases[cases < ncases].shape[0] == 0:
        return None
    last_lt_ncases = cases[cases < ncases].index[-1]
    offset_cases = 1 - ((ncases - cases.loc[last_lt_ncases])/(cases.loc[first_gte_ncases] - cases.loc[last_lt_ncases]))
    days_since_ncases = (current_date - first_gte_ncases).days + offset_cases
    return np.round(days_since_ncases, 3)

def compute_stats(item, grp, grouped_sum, iso3, current_date):
    keys = ["Confirmed", "Recovered", "Deaths"]
    api_keys = ["confirmed", "recovered", "dead"]
    sorted_group_sum = grouped_sum.loc[iso3]["Confirmed"].sort_index()
    item["mostRecent"] = (current_date == sorted_group_sum.index[-1])
    first_date = {}
    compute_num_increase = lambda x: sorted_group_sum[x] - sorted_group_sum[x - timedelta(days = 1)] if x - timedelta(days = 1) in sorted_group_sum.index else sorted_group_sum[x]
    for key,api_key in zip(keys, api_keys):
        sorted_group_sum = grouped_sum.loc[iso3][key].sort_index()
        item[api_key] = grp[key].sum()
        # Rolling mean
        tmp_grp = sorted_group_sum.reset_index()
        rolling_average = tmp_grp[(tmp_grp["date"]<=(current_date + timedelta(days = 3))) & (tmp_grp["date"] >= current_date - timedelta(days = 3))]["date"].apply(compute_num_increase)
        # Exclude negative values from lib import funs rolling average
        rolling_average = rolling_average[rolling_average >= 0].mean()
        if current_date in sorted_group_sum.index and not np.isnan(rolling_average):
            item[api_key+"_rolling"] = rolling_average
        # Compute rolling mean 2 weeks ago
        rolling_average_14days_ago = tmp_grp[(tmp_grp["date"]<=((current_date - timedelta(days=14)) + timedelta(days = 3))) & (tmp_grp["date"] >= (current_date - timedelta(days=14)) - timedelta(days = 3))]["date"].apply(compute_num_increase)
        rolling_average_14days_ago = rolling_average_14days_ago[rolling_average_14days_ago >= 0].mean() if rolling_average_14days_ago.shape[0] > 0 else np.nan
        if current_date in sorted_group_sum.index and not np.isnan(rolling_average_14days_ago):
            item[api_key+"_rolling_14days_ago"] = rolling_average_14days_ago
            if api_key + "_rolling" in item:
                item[api_key+"_rolling_14days_ago_diff"] = rolling_average - rolling_average_14days_ago
        # Doubling rate
        val_dr = tmp_grp[(tmp_grp["date"]<= current_date) & (tmp_grp["date"] >= current_date - timedelta(days = 4))][key].tolist()
        val_dr = [i for i in val_dr if i > 0]
        dr = compute_doubling_rate(val_dr) if len(val_dr) > 1 else np.nan
        if current_date in sorted_group_sum.index and not np.isnan(dr):
            item[api_key+"_doublingRate"] = dr
        # item[api_key+"_currentCases"] = sorted_group_sum.iloc[-1]
        # item[api_key+"_currentIncrease"] = sorted_group_sum.iloc[-1] - sorted_group_sum.iloc[-2] if len(sorted_group_sum) > 1 else sorted_group_sum.iloc[-1]
        # if len(sorted_group_sum) > 1 and sorted_group_sum.iloc[-2] !=0:
        #     item[api_key+"_currentPctIncrease"] = ((sorted_group_sum.iloc[-1] - sorted_group_sum.iloc[-2])/sorted_group_sum.iloc[-2])
        # item[api_key+"_currentToday"] = sorted_group_sum.index[-1].strftime("%Y-%m-%d")
        first_date[key] = sorted_group_sum[sorted_group_sum > 0].index[0] if sorted_group_sum[sorted_group_sum > 0].shape[0] > 0 else ""
        item[api_key+"_firstDate"] = first_date[key].strftime("%Y-%m-%d") if first_date[key] != "" else ""
        item[api_key+"_newToday"] = True if len(sorted_group_sum) > 1 and sorted_group_sum.iloc[-1] - sorted_group_sum.iloc[-2] > 0 else False
        item[api_key+"_numIncrease"] = compute_num_increase(current_date)

        if current_date - timedelta(days = 1) in sorted_group_sum.index and sorted_group_sum[current_date - timedelta(days = 1)] > 0:
            item[api_key+"_pctIncrease"] = (sorted_group_sum[current_date] - sorted_group_sum[current_date - timedelta(days = 1)])/sorted_group_sum[current_date - timedelta(days = 1)]

        if "population" in item and item["population"] > 0:
            per_capita_keys = [api_key, api_key+"_rolling", api_key+"_rolling_14days_ago", api_key+"_rolling_14days_ago_diff"]
            for per_capita_key in per_capita_keys:
                if per_capita_key not in item:
                    continue
                item[per_capita_key+"_per_100k"] = (item[per_capita_key]/item["population"]) * 100000
    if first_date["Confirmed"] != "" and first_date["Deaths"] != "":
        item["first_dead-first_confirmed"] = (first_date["Deaths"] - first_date["Confirmed"]).days
    # daysSince100Cases
    confirmed_cases = grouped_sum.loc[iso3]["Confirmed"].sort_index()
    days_since_100_cases = compute_days_since(confirmed_cases, 100, current_date)
    if days_since_100_cases != None and days_since_100_cases >= 0:
        item["daysSince100Cases"] = days_since_100_cases
    # daysSince10Deaths
    deaths = grouped_sum.loc[iso3]["Deaths"].sort_index()
    days_since_10_deaths = compute_days_since(deaths, 10, current_date)
    if days_since_10_deaths != None and days_since_10_deaths >= 0:
        item["daysSince10Deaths"] = days_since_10_deaths
    # daysSince50Deaths
    deaths = grouped_sum.loc[iso3]["Deaths"].sort_index()
    days_since_50_deaths = compute_days_since(deaths, 50, current_date)
    if days_since_50_deaths != None and days_since_50_deaths>=0:
        item["daysSince50Deaths"] = days_since_50_deaths

# Extract metropolitan area features
def get_metro_feat(cbsa, shp):
    feats = [i for i in shp if i["properties"]["CBSAFP"] == cbsa]
    if len(feats) == 0:
        logging.info("Couldn't find metro feature for CBSA code: {}".format(cbsa))
        return None
    return feats[0]

# Countries
def generate_country_item(ind_grp, grouped_sum, country_sub_national):
    (ind, grp) = ind_grp
    item = {
        "date": ind[1].strftime("%Y-%m-%d"),
        "name": grp["computed_country_name"].iloc[0],
        "country_name": grp["computed_country_name"].iloc[0],
        "iso3": grp["computed_country_iso3"].iloc[0],
        "lat": grp["Lat"].iloc[0],
        "long": grp["Long"].iloc[0],
        "population": grp["computed_country_pop"].iloc[0],
        "wb_region": grp["computed_region_wb"].iloc[0],
        "location_id" : format_id(grp["computed_country_iso3"].iloc[0]),
        "_id": format_id(grp["computed_country_iso3"].iloc[0] + "_" + ind[1].strftime("%Y-%m-%d")),
        "admin_level": 0,
        "lat": grp["computed_country_lat"].iloc[0],
        "long": grp["computed_country_long"].iloc[0],
        "num_subnational": int(country_sub_national[ind[0]]),
        "gdp_last_updated":grp["gdp_update_year"].iloc[0],
        "gdp_per_capita":grp["country_gdp"].iloc[0]  # For every date number of admin1 regions in country with reported cases.
    }
    compute_stats(item, grp, grouped_sum, ind[0], ind[1])
    return item

# States
def generate_state_item(ind_grp, grouped_sum, testing_columns):
    ind,grp = ind_grp
    item = {
        "date": ind[1].strftime("%Y-%m-%d"),
        "name": grp["computed_state_name"].iloc[0],
        "country_name": grp["computed_country_name"].iloc[0],
        "iso3": grp["computed_state_iso3"].iloc[0],
        "country_iso3": grp["computed_country_iso3"].iloc[0],
        "lat": grp["Lat"].iloc[0],
        "long": grp["Long"].iloc[0],
        "country_population": grp["computed_country_pop"].iloc[0],
        "wb_region": grp["computed_region_wb"].iloc[0],
        "location_id" : format_id(grp["computed_country_iso3"].iloc[0] +"_" + grp["computed_state_iso3"].iloc[0]),
        "_id": format_id(grp["computed_country_iso3"].iloc[0] +"_" + grp["computed_state_iso3"].iloc[0] + "_" + ind[1].strftime("%Y-%m-%d")),
        "admin_level": 1,
        "lat": grp["computed_state_lat"].iloc[0],
        "long": grp["computed_state_long"].iloc[0],
        "gdp_last_updated":grp["gdp_update_year"].iloc[0],
        "country_gdp_per_capita":grp["country_gdp"].iloc[0]
    }
    if grp["computed_country_iso3"].iloc[0] == "USA":
        for i in testing_columns:
            if pd.isna(grp[i].iloc[0]):
                continue
            item[i] = grp[i].iloc[0]
        pop = grp["computed_state_pop"].iloc[0]
        if not pd.isna(pop) and pop > 0:
            item["population"] = pop
            # Compute case stats
    compute_stats(item, grp, grouped_sum, ind[0], ind[1])
    return item

# Counties
def generate_county_item(ind_grp, grouped_sum):
    ind,grp = ind_grp
    item = {
        "date": ind[1].strftime("%Y-%m-%d"),
        "name": grp["computed_county_name"].iloc[0],
        "iso3": grp["computed_county_iso3"].iloc[0],
        "state_name": grp["computed_state_name"].iloc[0],
        "country_name": grp["computed_country_name"].iloc[0],
        "state_iso3": grp["computed_state_iso3"].iloc[0],
        "country_iso3": grp["computed_country_iso3"].iloc[0],
        "lat": grp["Lat"].iloc[0],
        "long": grp["Long"].iloc[0],
        "country_population": grp["computed_country_pop"].iloc[0],
        "wb_region": grp["computed_region_wb"].iloc[0],
        "location_id" : format_id(grp["computed_country_iso3"].iloc[0] +"_" + grp["computed_state_iso3"].iloc[0] + "_" + grp["computed_county_iso3"].iloc[0]),
        "_id": format_id(grp["computed_country_iso3"].iloc[0] +"_" + grp["computed_state_iso3"].iloc[0] + "_" + grp["computed_county_iso3"].iloc[0] + "_" + ind[1].strftime("%Y-%m-%d")),
        "admin_level": 2,
        "lat": grp["computed_county_lat"].iloc[0],
        "long": grp["computed_county_long"].iloc[0],
        "gdp_last_updated":grp["gdp_update_year"].iloc[0],
        "country_gdp_per_capita":grp["country_gdp"].iloc[0]
    }
    pop = grp["computed_county_pop"].iloc[0]
    state_pop = grp["computed_state_pop"].iloc[0]
    if not pd.isna(pop) and pop > 0:
        item["population"] = pop
    if not pd.isna(state_pop) and pop > 0:
        item["state_population"] = state_pop
    compute_stats(item, grp, grouped_sum, ind[0], ind[1])
    return item

# wb_region
def generate_region_item(ind_grp, grouped_sum):
    ind,grp = ind_grp
    item = {
        "date": ind[1].strftime("%Y-%m-%d"),
        "name": grp["computed_region_wb"].iloc[0],
        "iso3": grp["computed_region_wb"].iloc[0],
        "wb_region": grp["computed_region_wb"].iloc[0],
        "location_id" : format_id(grp["computed_region_wb"].iloc[0]),
        "_id": format_id(grp["computed_region_wb"].iloc[0] + "_" + ind[1].strftime("%Y-%m-%d")),
        "admin_level": -1
    }
    compute_stats(item, grp, grouped_sum, ind[0], ind[1])
    return item

# metropolitan areas
def generate_metro_item(ind_grp, grouped_sum, metro):
    ind,grp = ind_grp
    get_metro_counties = lambda x: metro[metro["CBSA Code"] == x][["County/County Equivalent", "State Name", "fips"]].rename(columns={"County/County Equivalent": "county_name", "State Name": "state_name"}).to_dict("records")
    item = {
        "date": ind[1].strftime("%Y-%m-%d"),
        "name": grp["computed_metro_name"].iloc[0],
        "cbsa": grp["computed_metro_cbsa"].iloc[0],
        "lat": grp["computed_metro_lat"].iloc[0],
        "long": grp["computed_metro_long"].iloc[0],
        "location_id" : format_id("METRO_"+grp["computed_metro_cbsa"].iloc[0]),
        "_id": format_id("METRO_"+grp["computed_metro_cbsa"].iloc[0] + "_" + ind[1].strftime("%Y-%m-%d")),
        "admin_level": 1.5,
        "country_name": grp["computed_country_name"].iloc[0],
        "sub_parts": get_metro_counties(grp["CBSA_Code"].iloc[0]),
        "wb_region": grp["computed_region_wb"].iloc[0]
    }
    pop = grp["computed_metro_pop"].iloc[0]
    if not pd.isna(pop) and pop > 0:
        item["population"] = pop
    compute_stats(item, grp, grouped_sum, ind[0], ind[1])
    return item

# Add testing data
def get_us_testing_data(admn1_shp):
    testing_api_url = "https://covidtracking.com/api/states/daily"
    us_states = [i for i in admn1_shp if i["properties"]["adm0_a3"] == "USA"]
    resp = requests.get(testing_api_url)
    us_testing = {}
    if resp.status_code != 200:
        logging.info("US testing data could not be obtained from https://covidtracking.com/api/states/daily.")
        return us_testing
    testing = resp.json()
    for feat in us_states:
        state_tests = [i for i in testing if i["state"] == feat["properties"]["i_3166_"][-2:]]
        if len(state_tests) > 0:
            for state_test in state_tests:
                d = {}
                current_date = None
                for k,v in state_test.items():
                    if v == None or k == "state":
                        continue
                    if k in ["lastUpdateEt", "checkTimeEt"] and type(v) != int and "/" in v:
                        v = dt.strptime("2020/"+v, "%Y/%m/%d %H:%M") if len(v.split("/")) == 2 else dt.strptime(v, "%m/%d/%Y %H:%M") # Deals with 1900 being default year for Feb 29th without year
                        v = v.strftime("2020-%m-%d %H:%M") 
                    if k  == "date":
                        current_date = dt.strptime(str(v), "%Y%m%d").strftime("%Y-%m-%d")
                    d[k] = v
                us_testing[current_date + "_" + feat["properties"]["i_3166_"]] = copy.deepcopy(d)
        else:
            logging.warning("No testing data for US State: {}".format(feat["properties"]["iso_3166_"]))
    return us_testing

def populate_country(x):
    country_attr = {
        "computed_country_name": "NAME",
        "computed_country_pop": "POP_EST",
        "computed_country_iso3": "ADM0_A3"
    }
    centroid = get_centroid(usa_country_feat["geometry"]) if x["Country_Region"] == "USA_NYT" else get_centroid(country_feats[(x["Lat"], x["Long"])]["geometry"])
    get_val = lambda x,v: usa_country_feat["properties"][v] if x["Country_Region"] == "USA_NYT" else country_feats[(x["Lat"], x["Long"])]["properties"][v]
    attr = dict([[k, get_val(x,v)] for k,v in country_attr.items()])
    attr.update({
        "computed_region_wb": country_feats[(x["Lat"], x["Long"])]["properties"]["REGION_WB"] + ": China" if x["computed_country_iso3"] == "CHN" else usa_country_feat["properties"]["REGION_WB"] if x["Country_Region"] == "USA_NYT" else country_feats[(x["Lat"], x["Long"])]["properties"]["REGION_WB"],
        "computed_country_long": centroid[0],
        "computed_country_lat": centroid[1]
    })
    return pd.Series(attr)

def populate_state(x):
    centroid = get_centroid(us_state_feats[x["fips"][:2]]["geometry"])
    attr = {
        "computed_state_long": centroid[0],
        "computed_state_lat": centroid[1],
        "computed_state_name": us_state_feats[x["fips"][:2]]["properties"]["name"],
        "computed_state_iso3": us_state_feats[x["fips"][:2]]["properties"]["i_3166_"],
        "computed_state_pop": us_state_feats[x["fips"][:2]]["properties"]["POPESTI"]
    }
    return pd.Series(attr)

def populate_non_us_state(x):
    cetroid = get_centroid(state_feats[(x["Lat"], x["Long"])]["geometry"])
    attr = {
        "computed_state_long": centroid[0],
        "computed_state_lat": centroid[1],
        "computed_state_name": state_feats[(x["Lat"], x["Long"])]["properties"]["name"],
        "computed_state_iso3": state_feats[(x["Lat"], x["Long"])]["properties"]["i_3166_"]
    }
    return pd.Series(attr)


def populate_us_county(x):
    cetroid = get_centroid(usa_admn2_feats[x["fips"]]["geometry"])
    attr = {
        "computed_county_long": centroid[0],
        "computed_county_lat": centroid[1],
        "computed_county_name": usa_admn2_feats[x["fips"]]["properties"]["NAMELSA"],
        "computed_county_iso3": usa_admn2_feats[x["fips"]]["properties"]["STATEFP"] + usa_admn2_feats[x["fips"]]["properties"]["COUNTYF"],
        "computed_county_pop": usa_admn2_feats[x["fips"]]["properties"]["POPESTI"]
    }
    return pd.Series(attr)

def populate_us_metro(x):
    centroid = get_centroid(metro_feats[x["CBSA_Code"]]["geometry"]) if metro_feats[x["CBSA_Code"]] != None else [None, None]
    attr = {
        "computed_metro_long": centroid[0],
        "computed_metro_lat": centroid[1],
        "computed_metro_cbsa": metro_feats[x["CBSA_Code"]]["properties"]["CBSAFP"] if metro_feats[x["CBSA_Code"]] != None else None,
        "computed_metro_name": metro_feats[x["CBSA_Code"]]["properties"]["NAME"] if metro_feats[x["CBSA_Code"]] != None else None,
        "computed_metro_pop": metro_feats[x["CBSA_Code"]]["properties"]["POPESTI"] if metro_feats[x["CBSA_Code"]] != None else None
    }
    return pd.Series(attr)
