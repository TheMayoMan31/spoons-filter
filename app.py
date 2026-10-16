import os
# app.py
from scraper import *

import streamlit as st
import requests
import plotly.express as px

tab1, tab2, tab3 = st.tabs(["Specific Location", "Scatter Graph", "Owl"])

with tab1:
    st.header("Specific Location")
    names = fetch_venue_names()
    option = st.selectbox("Enter a location name", names)
    sort_by = st.radio("Sort by", ["Name", "Price", "PPU"])

    options = st.multiselect(
        "Select filter: ",
        ALCOHOLIC_CATEGORIES,
        key="tab1_filter",
    )

    if st.button("Fetch Prices"):

        with st.spinner("Fetching prices from Wetherspoons..."):
            fetch_specific_venue(option)
            df = pd.read_csv('specificLocation.csv')

        drinksCategory = options

        if options:
            df = df[df['category'].str.lower().str.strip().isin(options)]

        if sort_by == "Name":
            st.dataframe(df.sort_values('productname'))
        elif sort_by == "Price":
            st.dataframe(df.sort_values('price'))
        elif sort_by == "PPU":
            st.dataframe(df.sort_values('ppu'))

with tab2:
    st.header("Scatter Graph")
    if not os.path.exists('specificLocation.csv'):
        st.info("Fetch prices in the first tab to generate data.")
        st.stop()
    df = pd.read_csv('specificLocation.csv')

    options = st.multiselect(
        "Select filter: ",
        ALCOHOLIC_CATEGORIES,
        key="tab2_filter",
    )

    drinksCategory = options

    if options:
        df = df[df['category'].str.lower().str.strip().isin(options)]

    drink_search = st.text_input(
        "Search for a drink to highlight",
        placeholder="e.g. Budweiser",
        key="graph_drink_search",
    ).strip()

    product_names = df['productname'].fillna('').astype(str)
    matching_drinks = (
        product_names.str.contains(drink_search, case=False, regex=False)
        if drink_search
        else pd.Series(False, index=df.index)
    )

    fig = px.scatter(
        df,
        x='price',
        y='units',
        hover_name='productname',
        trendline="ols",
    )
    fig.update_traces(
        marker={
            'color': [
                '#e74c3c' if is_match else '#7f8c8d'
                for is_match in matching_drinks
            ],
            'size': [
                12 if is_match else 7
                for is_match in matching_drinks
            ],
        },
    )

    if drink_search:
        match_count = int(matching_drinks.sum())
        if match_count:
            st.caption(f"Highlighted {match_count} matching portion(s).")
        else:
            st.caption("No matching drinks found.")

    st.plotly_chart(
        fig,
        alt="Drink price versus alcohol units, with matching drinks highlighted",
    )



with tab3:
    st.header("An owl")
