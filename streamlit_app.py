from xml.sax.handler import DTDHandler
from alpaca_trade_api.rest import REST, TimeFrame
import requests
import pandas as pd
import json
import streamlit as st
import datetime as dt
import pytz
from datetime import datetime, timedelta
from ta import volatility

st.set_page_config(layout='wide')
st.write('<style>div.row-widget.stRadio > div{flex-direction:row;}</style>', unsafe_allow_html=True)

trades_url = 'https://hhogib1lv4.execute-api.ca-central-1.amazonaws.com/prod/trades'
orders_url = 'https://hhogib1lv4.execute-api.ca-central-1.amazonaws.com/prod/orders'
watchlist_url = 'https://hhogib1lv4.execute-api.ca-central-1.amazonaws.com/prod/watchlist'


@st.cache(allow_output_mutation=True, ttl=3600)
def get_trades_table(url):
    res = requests.get(url)
    res = json.loads(res.text)
    return res['Result']


def get_watchlist_table(url):
    res = requests.get(url)
    res = json.loads(res.text)
    return res['Result']['Items']


# set up
trades_data = get_trades_table(trades_url)
watchlist_data = get_watchlist_table(watchlist_url)

trades = pd.DataFrame(trades_data)
trades = trades[trades['Tag'] != 'Error']
trades = trades[['Symbol', 'OpenDate', 'CloseDate', 'Direction', 'Quantity', 'InitEntry',
                 'Stop', 'Target', 'AvgEntry', 'AvgExit', 'PnL','Commission', 'Status', 'Updated', 'TradeID', 'Executions']]

trades['OpenDate'] = pd.to_datetime(trades['OpenDate'])
trades['OpenDate'] = trades['OpenDate'].apply(
    lambda x: x.strftime('%Y-%m-%d %H:%M:%S'))

trades['CloseDate'] = pd.to_datetime(trades['CloseDate'], errors='coerce')
trades['CloseDate'] = trades['CloseDate'].apply(
    lambda x: x.strftime('%Y-%m-%d %H:%M:%S') if x is not pd.NaT else x)

trades['Updated'] = pd.to_datetime(trades['Updated'])
trades['Updated'] = trades['Updated'].apply(
    lambda x: x.strftime('%Y-%m-%d %H:%M:%S'))

trades = trades.sort_values(by=['Updated'], ascending=False)
trades = trades[trades['OpenDate'] > '2022-03-20']

symbol = st.selectbox(
    'Symbol:', ['ALL'] + sorted(set(trades['Symbol'].to_list())), index=0)

if symbol == 'ALL':
    trades = trades
else:
    trades = trades[trades['Symbol'] == symbol]

watchlist = pd.DataFrame(watchlist_data)

# render
st.dataframe(trades)
st.write(f"P&L: {round(trades['PnL'].sum(),5)}, Com: {round(trades['Commission'].sum(),5)}")
watchlist = watchlist[['Symbol', 'Direction',
                       'Entry', 'Stop', 'Target','Quantity', 'Added', 'State']]

one, two = st.columns([1, 1])
with two:
    item_index = st.multiselect(
        label='Select item Index:', options=watchlist.index.tolist())
    deactivate_item = st.button('Deactivate Item')
    if deactivate_item:
        for i in item_index:
            request_body = {
                "Symbol": f"{watchlist.loc[i,'Symbol']}",
                "Added": f"{watchlist.loc[i,'Added']}",
                "UpdateKey": "State",
                "UpdateValue": "Inactive",
            }
            res = requests.patch(watchlist_url, json=request_body)

        st.experimental_rerun()

with one:
    watchlist_view = st.radio(label='Choose View', options=[
                              'Active', 'All'])
    watchlist['Added'] = pd.to_datetime(watchlist['Added'])
    watchlist['Added'] = watchlist['Added'].apply(
        lambda x: x.strftime('%Y-%m-%d %H:%M:%S'))
    if watchlist_view == 'Active':
        watchlist = watchlist[watchlist['State'] == 'Active']
    else:
        watchlist = watchlist
    st.dataframe(watchlist)

# sidebar
APCA_API_KEY_ID = "PKCOE43ZGVUG1ISZ0XLB"
APCA_API_SECRET_KEY = "eaPBs6e9RFxaS5kNHUuszPwoS7E1r6Y2oExrSQsh"
APCA_API_BASE_URL = "https://paper-api.alpaca.markets"
apca_api = REST(APCA_API_KEY_ID, APCA_API_SECRET_KEY, APCA_API_BASE_URL)


@st.cache(allow_output_mutation=True, ttl=86400)
def get_symbol_list():
    symbol_list = apca_api.list_assets(
        status='active', asset_class='us_equity')
    symbol_list = [i.symbol for i in symbol_list]
    return sorted(symbol_list)


@st.cache(allow_output_mutation=True, ttl=3600)
def get_eod_data(symbol, warmup=0):
    warmup_time = timedelta(warmup)
    one_year = (datetime.today() - timedelta(days=365)).date()
    bars = apca_api.get_bars(symbol, TimeFrame.Day,
                             start=one_year - warmup_time, adjustment='all').df
    bars.index = bars.index.tz_convert('America/New_York').date
    return bars


symbol_list = get_symbol_list()

st.sidebar.header('Position Size Calculator')
symbol = st.sidebar.selectbox('Select symbol:', options=symbol_list)

risk_options = [10, 20, 30, 50, 80, 100]
risk = st.sidebar.selectbox(label='$ Risk', options=risk_options, index=1)
entry = st.sidebar.number_input(label='Entry', value=2.00, step=0.1)
stop = st.sidebar.number_input(label='Stop', value=1.00, step=0.1)
target = entry + (entry - stop)
distance = round(entry - stop, 2)
size = round(risk / abs(distance), 3)
direction = 'Long' if distance > 0 else 'Short'
st.sidebar.number_input('Target', min_value=target,
                        max_value=target, value=target)
st.sidebar.write(f'Direction: {direction}')
st.sidebar.subheader(f'Size: {size} share' if size ==
                     1 else f'Size: {size} shares')

bars = get_eod_data(symbol)
bars = bars.fillna('N/A')
bars['ATR'] = volatility.AverageTrueRange(bars['high'], bars['low'], bars['close'],
                                          window=21).average_true_range()
atr = bars.iloc[-1]['ATR']
st.sidebar.write(
    f"Distance: {abs(distance)},    ATR: {round(atr, 2)},    Stop/ATR: {round(distance / atr, 2)}")
watchlist_send = st.sidebar.button('Send to Watchlist')
st.sidebar.write('')


if watchlist_send:
    updated = dt.datetime.now(pytz.timezone(
        'America/Chicago')).isoformat(timespec='seconds')
    request_body = {
        "Symbol": f"{symbol}",
        "Direction": f"{direction}",
        "Entry": f"{entry}",
        "Stop": f"{stop}",
        "Target": f"{target}",
        "Added": f"{updated}",
        "Quantity":f"{size}",
        "State": "Active"
    }
    requests.post(watchlist_url, json=request_body)
    st.experimental_rerun()


# send_update_request = st.button('Send Update Request')
# if send_update_request:

# url = 'https://httpbin.org/patch'
# payload = {
#     'website':'softhunt.net',
#     'courses':['Python','JAVA']
#     }
# response = requests.patch(url, data=payload)
