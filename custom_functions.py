import pandas as pd
import numpy as np
from io import BytesIO
import streamlit as st
import plotly.express as px  # pip install plotly-express
import plotly.io as pio
import plotly.graph_objects as go
from PIL import Image
import boto3
from datetime import datetime
from botocore.exceptions import ClientError
import requests
import json

######################
# Initialize variables
######################
# background nutanix logo for diagrams
background_image = dict(source=Image.open("images/nutanix-x.png"), xref="paper", yref="paper", x=0.5, y=0.5, sizex=0.95, sizey=0.95, xanchor="center", yanchor="middle", opacity=0.04, layer="below", sizing="contain")

######################
# Custom Functions
######################
# Use local CSS
def local_css(file_name):
    with open(file_name) as f:
        #st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
        return f.read()

# Generate Dataframe from Excel and make neccessary adjustment for easy consumption later on
@st.cache(allow_output_mutation=True)
def get_data_from_excel(uploaded_file):

    df = pd.ExcelFile(uploaded_file, engine="openpyxl")

    # Columns to read from Excel file
    vInfo_cols_to_use = ['VM','Powerstate','CPUs','Memory','Provisioned MiB','In Use MiB','Datacenter','Cluster','Host','OS according to the configuration file','OS according to the VMware Tools','VM ID']
    vCPU_cols_to_use = ['VM','Powerstate','CPUs','Cluster','VM ID']
    vMemory_cols_to_use = ['VM','Powerstate','Size MiB','Cluster','VM ID']
    vDisk_cols_to_use = ['Powerstate', 'Capacity MiB', 'Thin','Cluster','VM ID']
    vPartition_cols_to_use = ['Powerstate', 'Capacity MiB','Consumed MiB','Cluster','VM ID']
    vHosts_cols_to_use = ['Cluster', 'Speed', '# CPU', 'Cores per CPU', '# Cores','CPU usage %', '# Memory', 'Memory usage %', '# VMs']
    vDatastore_cols_to_use = ['Capacity MiB','Provisioned MiB','In Use MiB','Object ID']

    # Create df for each tab with only relevant columns
    df_vInfo = df.parse('vInfo', usecols=vInfo_cols_to_use)
    df_vCPU = df.parse('vCPU', usecols=vCPU_cols_to_use)
    df_vMemory = df.parse('vMemory', usecols=vMemory_cols_to_use)
    df_vDisk = df.parse('vDisk', usecols=vDisk_cols_to_use)
    df_vPartition = df.parse('vPartition', usecols=vPartition_cols_to_use)
    df_vHosts = df.parse('vHost', usecols=vHosts_cols_to_use)
    df_vDataStore = df.parse('vDatastore', usecols=vDatastore_cols_to_use)

    return df_vInfo, df_vCPU, df_vMemory, df_vDisk, df_vPartition, df_vHosts, df_vDataStore

# Generate pCPU, pMemory & vDatastore information for vCluster section
def generate_donut_charts(usage_percentage):

    donut_chart = go.Figure(data = go.Pie(values = usage_percentage, hole = 0.9, marker_colors=['#034EA2','#BBE3F3'], sort=False,textinfo='none', hoverinfo='skip'))
    donut_chart.add_annotation(x= 0.5, y = 0.5, text = str(round(usage_percentage[0],2))+' %', font = dict(size=20,family='Arial Black', color='black'), showarrow = False)
    donut_chart.update(layout_showlegend=False)
    donut_chart.update_layout(margin=dict(l=10, r=10, t=10, b=10,pad=4), autosize=True, height = 150)
    donut_chart_config = {'staticPlot': True}

    return donut_chart, donut_chart_config

# Upload File to AWS for troubleshooting
def upload_to_aws(data):
    s3_client = boto3.client('s3', aws_access_key_id=st.secrets["s3_access_key_id"],
                      aws_secret_access_key=st.secrets["s3_secret_access_key"])

    current_datetime_as_filename = datetime.now().strftime("%Y_%m_%d-%I_%M_%S_%p")+".xlsx"
    
    try:
        s3_client.put_object(Bucket=st.secrets["s3_bucket_name"], Body=data.getvalue(), Key=current_datetime_as_filename)
        #st.session_state[data.name] = True # store uploaded filename as sessionstate variable in order to block reupload of same file
        return True
    except FileNotFoundError:
        return False

# Generate CPU information for vCluster section
@st.cache(allow_output_mutation=True)
def generate_CPU_infos(df_vHosts_filtered):

    total_ghz = (df_vHosts_filtered['# Cores'] * df_vHosts_filtered['Speed']) / 1000
    consumed_ghz = (df_vHosts_filtered['# Cores'] * df_vHosts_filtered['Speed'] * (df_vHosts_filtered['CPU usage %']/100)) / 1000
    cpu_percentage_temp = consumed_ghz.sum() / total_ghz.sum() * 100
    cpu_percentage = [cpu_percentage_temp, (100-cpu_percentage_temp)]

    return  round(total_ghz.sum(),2), round(consumed_ghz.sum(),2), cpu_percentage

# Generate Memory information for vCluster section
@st.cache(allow_output_mutation=True)
def generate_Memory_infos(df_vHosts_filtered):

    total_memory = df_vHosts_filtered['# Memory'] / 1024
    consumed_memory = (df_vHosts_filtered['# Memory'] * (df_vHosts_filtered['Memory usage %']/100)) / 1024
    memory_percentage_temp = df_vHosts_filtered["Memory usage %"].mean()
    memory_percentage = [memory_percentage_temp, (100-memory_percentage_temp)]

    return  round(total_memory.sum(),2), round(consumed_memory.sum(),2), memory_percentage

# Generate vDatastore information for vCluster section
@st.cache(allow_output_mutation=True)
def generate_Storage_infos(df_vDataStore):

    storage_consumed = df_vDataStore['In Use MiB'].sum() / 1048576 # convert to TiB
    storage_provisioned = df_vDataStore['Provisioned MiB'].sum() / 1048576 # convert to TiB

    storage_percentage_temp = storage_consumed / storage_provisioned * 100
    storage_percentage = [storage_percentage_temp, storage_provisioned]

    return  round(storage_provisioned,2), round(storage_consumed,2), storage_percentage

# Generate vHost Overview Section
@st.cache(allow_output_mutation=True)
def generate_vHosts_overview_df(df_vHosts_filtered):

    # Generate Dataframe for pCPU Details
    consumed_ghz = str(round(((df_vHosts_filtered['# Cores'] * df_vHosts_filtered['Speed'] * (df_vHosts_filtered['CPU usage %']/100)) / 1000).sum(),2))+' Ghz'
    total_ghz = str(round(((df_vHosts_filtered['# Cores'] * df_vHosts_filtered['Speed']) / 1000).sum(),2))+' Ghz'
    
    max_core_amount = str(round(df_vHosts_filtered['# Cores'].max(),2))
    max_frequency_amount = str(round(df_vHosts_filtered['Speed'].max()/1000,2))+' Ghz'
    average_frequency_amount = str(round(df_vHosts_filtered['Speed'].mean()/1000,2))+' Ghz'
    max_usage_amount = str(round(df_vHosts_filtered['CPU usage %'].fillna(0).max(),2))+' %'
    average_usage_amount = str(round(df_vHosts_filtered['CPU usage %'].fillna(0).mean(),2))+' %'
    pCPU_first_column_df = {'': ["Ghz in Benutzung","Total Ghz","Max Core pro Host", "Max Taktrate / Prozessor", "Ø Taktrate / Prozessor", "Max CPU Nutzung", "Ø CPU Nutzung"]}
    pCPU_df = pd.DataFrame(pCPU_first_column_df)
    pCPU_second_column = [consumed_ghz, total_ghz, max_core_amount, max_frequency_amount, average_frequency_amount,max_usage_amount,average_usage_amount]
    pCPU_df.loc[:,'Werte'] = pCPU_second_column

    # Generate Dataframe for pMemory Details
    consumed_memory = str(round(((df_vHosts_filtered['# Memory'] * (df_vHosts_filtered['Memory usage %']/100))/1024).sum(),2))+' GiB'
    total_memory = str(round((df_vHosts_filtered['# Memory'].sum()/1024),2))+' GiB'    
    max_pRAM_amount = str(round((df_vHosts_filtered['# Memory'].max()/1024),2))+' GiB'
    max_pRAM_usage = str(round(df_vHosts_filtered['Memory usage %'].fillna(0).max(),2))+' %'
    average_pRAM_usage = str(round(df_vHosts_filtered['Memory usage %'].fillna(0).mean(),2))+' %'
    memory_first_column_df = {'': ["pMemory in Benutzung","Total pMemory","Max pMemory pro Host", "Max pMemory Nutzung","Ø pMemory Nutzung"]}
    memory_df = pd.DataFrame(memory_first_column_df)
    memory_second_column = [consumed_memory, total_memory, max_pRAM_amount, max_pRAM_usage, average_pRAM_usage]
    memory_df.loc[:,'Werte'] = memory_second_column

    # Generate Dataframe for vHost Details
    host_amount = str(round(df_vHosts_filtered.shape[0])) # get amount of rows / hosts
    sockets_amount = str(round(df_vHosts_filtered['# CPU'].sum()))
    cores_amount = str(round(df_vHosts_filtered['# Cores'].sum()))
    max_vm_host = str(round(df_vHosts_filtered['# VMs'].max()))
    average_vm_host = str(round(df_vHosts_filtered['# VMs'].mean(),2))
    hardware_first_column_df = {'': ["Anzahl Hosts", "Anzahl pSockets","Anzahl pCores", "Max VM pro Host (On)", "Ø VM pro Host (On)"]}
    hardware_df = pd.DataFrame(hardware_first_column_df)
    hardware_second_column = [host_amount, sockets_amount, cores_amount, max_vm_host, average_vm_host]
    hardware_df.loc[:,'Werte'] = hardware_second_column

    return pCPU_df, memory_df, hardware_df

# Generate Top10 VMs based on vCPU (on)
@st.cache(allow_output_mutation=True)
def generate_top10_vCPU_VMs_df(df_vInfo_filtered_vm_on):

    top_vms_vCPU = df_vInfo_filtered_vm_on[['VM','CPUs']].nlargest(10,'CPUs')

    return top_vms_vCPU

# Generate Top10 VMs based on vCPU (on)
@st.cache(allow_output_mutation=True)
def generate_top10_vMemory_VMs_df(df_vInfo_filtered_vm_on):

    top_vms_vMemory = df_vInfo_filtered_vm_on[['VM','Memory']].nlargest(10,'Memory')
    top_vms_vMemory.loc[:,"Memory"] = top_vms_vMemory["Memory"] / 1024
    top_vms_vMemory.rename(columns={'Memory': 'Memory (GiB)'}, inplace=True) # Rename Column
    top_vms_vMemory = top_vms_vMemory.style.format(precision=0) 

    return top_vms_vMemory

# Generate Top10 VMs based on vStorage consumed
@st.cache(allow_output_mutation=True)
def generate_top10_vStorage_consumed_VMs_df(df_vmList_filtered):

    top_vms_vStorage_consumed = df_vmList_filtered[['VM','In Use MiB']].nlargest(10,'In Use MiB')
    top_vms_vStorage_consumed.loc[:,"In Use MiB"] = top_vms_vStorage_consumed["In Use MiB"] / 1048576 # convert MiB zu TiB
    top_vms_vStorage_consumed.rename(columns={'In Use MiB': 'In Use (TiB)'}, inplace=True) # Rename Column
    top_vms_vStorage_consumed = top_vms_vStorage_consumed.style.format(precision=2) 

    return top_vms_vStorage_consumed

# Generate Guest OS df
@st.cache(allow_output_mutation=True)
def generate_guest_os_df(df_vInfo_filtered):

    guest_os_df_config = df_vInfo_filtered['OS according to the configuration file'].value_counts()
    guest_os_df_config = guest_os_df_config.reset_index()
    guest_os_df_config.rename(columns={'index': ''}, inplace=True)
    guest_os_df_config.rename(columns={'OS according to the configuration file': 'Guest OS'}, inplace=True) # Rename Column

    guest_os_df_tools = df_vInfo_filtered['OS according to the VMware Tools'].value_counts()
    guest_os_df_tools = guest_os_df_tools.reset_index()
    guest_os_df_tools.rename(columns={'index': ''}, inplace=True)
    guest_os_df_tools.rename(columns={'OS according to the VMware Tools': 'Guest OS'}, inplace=True) # Rename Column

    return guest_os_df_config, guest_os_df_tools

# Generate vHost Overview Section
@st.cache(allow_output_mutation=True)
def generate_vRAM_overview_df(df_vMemory_filtered):
    
    df_vMemory_filtered_on = df_vMemory_filtered.query("`Powerstate`=='poweredOn'")
    df_vMemory_filtered_off = df_vMemory_filtered.query("`Powerstate`=='poweredOff'")
    df_vMemory_filtered_suspended = df_vMemory_filtered.query("`Powerstate`=='suspended'")

    vRAM_provisioned_on = df_vMemory_filtered_on['Size MiB'].sum()/1024
    vRAM_provisioned_off = df_vMemory_filtered_off['Size MiB'].sum()/1024
    vRAM_provisioned_suspended = df_vMemory_filtered_suspended['Size MiB'].sum()/1024
    vRAM_provisioned_total = df_vMemory_filtered['Size MiB'].sum()/1024
    vRAM_provisioned_max_on = df_vMemory_filtered_on['Size MiB'].max()/1024
    vRAM_provisioned_average_on = df_vMemory_filtered_on['Size MiB'].mean()/1024
    vRAM_provisioned_first_column_df = {'': ["vMemory - On","vMemory - Off","vMemory - Suspended","vMemory - Total", "Max vMemory pro VM (On)","Ø vMemory pro VM (On)"]}
    vRAM_provisioned_df = pd.DataFrame(vRAM_provisioned_first_column_df)
    vRAM_provisioned_second_column = [vRAM_provisioned_on, vRAM_provisioned_off, vRAM_provisioned_suspended, vRAM_provisioned_total,vRAM_provisioned_max_on,vRAM_provisioned_average_on]
    vRAM_provisioned_df.loc[:,'GiB'] = vRAM_provisioned_second_column
    vRAM_provisioned_df = vRAM_provisioned_df.style.format(precision=2, na_rep='nicht vorhanden')

    return vRAM_provisioned_df

# Generate vCPU overview
@st.cache(allow_output_mutation=True)
def generate_vCPU_overview_df(df_vCPU_filtered,df_vHosts_filtered):
    
    df_vCPU_filtered_on = df_vCPU_filtered.query("`Powerstate`=='poweredOn'")
    df_vCPU_filtered_off = df_vCPU_filtered.query("`Powerstate`=='poweredOff'")
    df_vCPU_filtered_suspended = df_vCPU_filtered.query("`Powerstate`=='suspended'")

    vCPU_provisioned_on = df_vCPU_filtered_on['CPUs'].sum()
    vCPU_provisioned_off = df_vCPU_filtered_off['CPUs'].sum()
    vCPU_provisioned_suspended = df_vCPU_filtered_suspended['CPUs'].sum()
    vCPU_provisioned_total = df_vCPU_filtered['CPUs'].sum()
    vCPU_provisioned_max_on = df_vCPU_filtered_on['CPUs'].max()
    vCPU_provisioned_average_on = df_vCPU_filtered_on['CPUs'].mean()
    vCPU_provisioned_core_on = df_vCPU_filtered_on['CPUs'].sum() / df_vHosts_filtered['# Cores'].sum()

    if df_vHosts_filtered.shape[0] > 1: # Make sure more than 1 host
        vCPU_provisioned_core_on_n_1 = df_vCPU_filtered_on['CPUs'].sum() / ((df_vHosts_filtered['# Cores'].sum() / df_vHosts_filtered.shape[0]) * (df_vHosts_filtered.shape[0]-1))
        vCPU_provisioned_core_total_n_1 = df_vCPU_filtered['CPUs'].sum() / ((df_vHosts_filtered['# Cores'].sum() / df_vHosts_filtered.shape[0]) * (df_vHosts_filtered.shape[0]-1))
    else: # in case of single node
        vCPU_provisioned_core_on_n_1 = 0
        vCPU_provisioned_core_total_n_1 = 0

    vCPU_provisioned_core_total = df_vCPU_filtered['CPUs'].sum() / df_vHosts_filtered['# Cores'].sum()
    vCPU_provisioned_first_column_df = {'': ["vCPU - On","vCPU - Off","vCPU - Suspended","vCPU - Total", "Max vCPU pro VM (On)","Ø vCPU pro VM (On)", "vCPU pro Core (On)", "vCPU pro Core bei N-1 (On)", "vCPU pro Core (Total)", "vCPU pro Core bei N-1 (Total)"]}
    vCPU_provisioned_df = pd.DataFrame(vCPU_provisioned_first_column_df)
    vCPU_provisioned_second_column = [vCPU_provisioned_on, vCPU_provisioned_off, vCPU_provisioned_suspended, vCPU_provisioned_total,vCPU_provisioned_max_on,vCPU_provisioned_average_on,vCPU_provisioned_core_on,vCPU_provisioned_core_on_n_1,vCPU_provisioned_core_total,vCPU_provisioned_core_total_n_1]

    vCPU_provisioned_df.loc[:,'vCPUs'] = vCPU_provisioned_second_column
    vCPU_provisioned_df = vCPU_provisioned_df.style.format(precision=2, na_rep='nicht vorhanden') 

    return vCPU_provisioned_df

# Generate vStorage overview df's
@st.cache(allow_output_mutation=True)
def generate_vStorage_overview_df(df_vDisk_filtered,df_vPartition_filtered,df_vDataStore,df_vInfo_filtered):
    
    ########################
    ## vPartition Auswertung
    ########################
    df_vPartition_filtered_on = df_vPartition_filtered.query("`Powerstate`=='poweredOn'")
    df_vPartition_filtered_off = df_vPartition_filtered.query("`Powerstate`=='poweredOff' | `Powerstate`=='suspended'")
    vPartition_amount_vms = str(df_vPartition_filtered['VM ID'].nunique())
    vPartition_amount_on = str(df_vPartition_filtered_on.shape[0])
    vPartition_amount_off = str(df_vPartition_filtered_off.shape[0])
    vPartition_amount_total = str(df_vPartition_filtered.shape[0])
    vPartition_capacity_on = str(round(df_vPartition_filtered_on['Capacity MiB'].sum() / 1048576,2))+" TiB"
    vPartition_capacity_off = str(round(df_vPartition_filtered_off['Capacity MiB'].sum() / 1048576,2))+" TiB"
    vPartition_capacity_total = str(round(df_vPartition_filtered['Capacity MiB'].sum() / 1048576,2))+" TiB"
    vPartition_capacity_consumed_on = str(round(df_vPartition_filtered_on['Consumed MiB'].sum() / 1048576,2))+" TiB"
    vPartition_capacity_consumed_off = str(round(df_vPartition_filtered_off['Consumed MiB'].sum() / 1048576,2))+" TiB"
    vPartition_capacity_consumed_total = str(round(df_vPartition_filtered['Consumed MiB'].sum() / 1048576,2))+" TiB"
    vPartition_first_column_df = {'': [
            "Anzahl VMs mit vPartitions", "Anzahl vPartition (On)", "Anzahl vPartition (Off/Suspended)", "Anzahl vPartition (Total)",
            "Capacity consumed (On)", "Capacity consumed (Off/Suspended)", "Capacity consumed (Total)",
            "Capacity provisioned (On)", "Capacity provisioned (Off/Suspended)", "Capacity provisioned (Total)"
        ]}
    vPartition_df = pd.DataFrame(vPartition_first_column_df)
    vPartition_df = vPartition_df.astype(str)
    vPartition_second_column_df = [
            vPartition_amount_vms, vPartition_amount_on, vPartition_amount_off, vPartition_amount_total, 
            vPartition_capacity_consumed_on, vPartition_capacity_consumed_off, vPartition_capacity_consumed_total,
            vPartition_capacity_on, vPartition_capacity_off, vPartition_capacity_total,
            
        ]
    vPartition_df.loc[:,'Werte'] = vPartition_second_column_df
    
    ########################
    ## vDisk Auswertung
    ########################
    df_vDisk_filtered_on = df_vDisk_filtered.query("`Powerstate`=='poweredOn'")
    df_vDisk_filtered_off = df_vDisk_filtered.query("`Powerstate`=='poweredOff' | `Powerstate`=='suspended'")
    df_vDisk_filtered_on_thin = df_vDisk_filtered_on.query("`Thin`==True")
    df_vDisk_filtered_off_thin = df_vDisk_filtered_off.query("`Thin`==True")
    df_vDisk_filtered_total_thin = df_vDisk_filtered.query("`Thin`==True")
    vDisk_amount_vms = str(df_vDisk_filtered['VM ID'].nunique())
    vDisk_amount_on = str(df_vDisk_filtered_on.shape[0])+" ("+str(df_vDisk_filtered_on_thin.shape[0])+" Thin)"
    vDisk_amount_off = str(df_vDisk_filtered_off.shape[0])+" ("+str(df_vDisk_filtered_off_thin.shape[0])+" Thin)"
    vDisk_amount_total = str(df_vDisk_filtered.shape[0])+" ("+str(df_vDisk_filtered_total_thin.shape[0])+" Thin)"
    vDisk_capacity_on = str(round(df_vDisk_filtered_on['Capacity MiB'].sum() / 1048576,2))+" TiB"
    vDisk_capacity_off = str(round(df_vDisk_filtered_off['Capacity MiB'].sum() / 1048576,2))+" TiB"
    vDisk_capacity_total = str(round(df_vDisk_filtered['Capacity MiB'].sum() / 1048576,2))+" TiB"
    vDisk_first_column_df = {'': [
            "Anzahl VMs mit vDisks", "Anzahl vDisk (On)", "Anzahl vDisk (Off/Suspended)","Anzahl vDisk (Total)",
            "Capacity (On)", "Capacity (Off/Suspended)", "Capacity (Total)"
        ]}
    vDisk_df = pd.DataFrame(vDisk_first_column_df)
    vDisk_second_column_df = [
            vDisk_amount_vms, vDisk_amount_on, vDisk_amount_off, vDisk_amount_total,
            vDisk_capacity_on, vDisk_capacity_off, vDisk_capacity_total
        ]
    vDisk_df.loc[:,'Werte'] = vDisk_second_column_df

    ########################
    ## vDataStore Auswertung
    ########################
    vDataStore_amount = str(df_vDataStore['Object ID'].nunique())
    vDataStore_capacity = str(round(df_vDataStore['Capacity MiB'].sum() / 1048576,2))+" TiB"
    vDataStore_provisioned = str(round(df_vDataStore['Provisioned MiB'].sum() / 1048576,2))+" TiB"
    vDataStore_in_use = str(round(df_vDataStore['In Use MiB'].sum() / 1048576,2))+" TiB"
    vDataStore_free_percentage = str(int((1-(round(df_vDataStore['In Use MiB'].sum() / df_vDataStore['Provisioned MiB'].sum(),2)))*100))+' %'
    vDataStore_first_column_df = {'': ["Anzahl vDatastores", "Capacity", "Provisioned","In Use", "Free"]}
    vDataStore_df = pd.DataFrame(vDataStore_first_column_df)
    vDataStore_second_column_df = [
            vDataStore_amount,vDataStore_capacity,vDataStore_provisioned,vDataStore_in_use,vDataStore_free_percentage
        ]
    vDataStore_df.loc[:,'Werte'] = vDataStore_second_column_df

    ########################
    ## VM Storage Auswertung
    ########################
    # Get VMs not in vPartition, get Disk for thoise vms and calculate Size for those missing disks
    VMs_not_in_vPartition_with_duplicates = pd.merge(df_vDisk_filtered[['VM ID']],df_vPartition_filtered[['VM ID']],on='VM ID', how='left', indicator=True).query("`_merge`=='left_only'").drop("_merge", 1)
    VMs_not_in_vPartition_unique = VMs_not_in_vPartition_with_duplicates.drop_duplicates(subset=['VM ID'])
    vDisks_not_in_vPartition = pd.merge(VMs_not_in_vPartition_unique[['VM ID']],df_vDisk_filtered[['Powerstate', 'Capacity MiB', 'VM ID']],on='VM ID', how='inner', indicator=True).query("`_merge`=='both'").drop("_merge", 1)
    vDisk_for_VMs_not_in_vPartition_filtered_on = vDisks_not_in_vPartition.query("`Powerstate`=='poweredOn'")
    vDisk_for_VMs_not_in_vPartition_filtered_on_value = round(vDisk_for_VMs_not_in_vPartition_filtered_on['Capacity MiB'].sum() / 1048576,2)
    vDisk_for_VMs_not_in_vPartition_filtered_off = vDisks_not_in_vPartition.query("`Powerstate`=='poweredOff' | `Powerstate`=='suspended'")
    vDisk_for_VMs_not_in_vPartition_filtered_off_value = round(vDisk_for_VMs_not_in_vPartition_filtered_off['Capacity MiB'].sum() / 1048576,2)      
    vDisk_for_VMs_not_in_vPartition_filtered_total_value = round(vDisks_not_in_vPartition['Capacity MiB'].sum() / 1048576,2)    
    df_vInfo_filtered_on = df_vInfo_filtered.query("`Powerstate`=='poweredOn'")
    df_vInfo_filtered_off = df_vInfo_filtered.query("`Powerstate`=='poweredOff' | `Powerstate`=='suspended'")
    df_vInfo_amount_on = str(df_vInfo_filtered_on.shape[0])
    df_vInfo_amount_off = str(df_vInfo_filtered_off.shape[0])
    df_vInfo_amount_total = str(df_vInfo_filtered.shape[0])
    df_vPartition_filtered_on = df_vPartition_filtered.query("`Powerstate`=='poweredOn'")
    df_vPartition_filtered_off = df_vPartition_filtered.query("`Powerstate`=='poweredOff' | `Powerstate`=='suspended'")
    vm_storage_capacity_on = str(round((df_vPartition_filtered_on['Capacity MiB'].sum() / 1048576) + vDisk_for_VMs_not_in_vPartition_filtered_on_value,2))+" TiB"
    vm_storage_capacity_off = str(round((df_vPartition_filtered_off['Capacity MiB'].sum() / 1048576) + vDisk_for_VMs_not_in_vPartition_filtered_off_value,2))+" TiB"
    vm_storage_capacity_total = str(round((df_vPartition_filtered['Capacity MiB'].sum() / 1048576) + vDisk_for_VMs_not_in_vPartition_filtered_total_value,2))+" TiB"    
    vDisk_for_VMs_not_in_vPartition_filtered_on_value_80 = vDisk_for_VMs_not_in_vPartition_filtered_on_value * 0.8
    vDisk_for_VMs_not_in_vPartition_filtered_off_value_80 = vDisk_for_VMs_not_in_vPartition_filtered_off_value * 0.8
    vDisk_for_VMs_not_in_vPartition_filtered_total_value_80 = vDisk_for_VMs_not_in_vPartition_filtered_total_value * 0.8
    vm_storage_consumed_on = str(round((df_vPartition_filtered_on['Consumed MiB'].sum() / 1048576)+(vDisk_for_VMs_not_in_vPartition_filtered_on_value_80),2))+" TiB"
    vm_storage_consumed_off = str(round((df_vPartition_filtered_off['Consumed MiB'].sum() / 1048576)+(vDisk_for_VMs_not_in_vPartition_filtered_off_value_80),2))+" TiB"
    vm_storage_consumed_total = str(round((df_vPartition_filtered['Consumed MiB'].sum() / 1048576)+(vDisk_for_VMs_not_in_vPartition_filtered_total_value_80),2))+" TiB"
    vm_storage_first_column_df = {'VMs': [
            "Anzahl VMs (On)", "Anzahl VMs (Off/Suspended)", "Anzahl VMs (Total)",
            "VM Consumed Capacity (On)", "VM Consumed Capacity (Off/Suspended)", "VM Consumed Capacity (Total)",
            "VM Provisioned Capacity (On)", "VM Provisioned Capacity (Off/Suspended)", "VM Provisioned Capacity (Total)"            
        ]}
    vm_storage_df = pd.DataFrame(vm_storage_first_column_df)
    vm_storage_second_column_df = [
            df_vInfo_amount_on, df_vInfo_amount_off, df_vInfo_amount_total,
            vm_storage_consumed_on, vm_storage_consumed_off, vm_storage_consumed_total,
            vm_storage_capacity_on, vm_storage_capacity_off, vm_storage_capacity_total            
        ]
    vm_storage_df.loc[:,'Werte'] = vm_storage_second_column_df

    ########################
    ## vInfo Auswertung
    ########################
    # Note: reuse vInfo filtered from VM Storage Auswertung (df_vInfo_filtered_on / df_vInfo_filtered_off / df_vInfo_filtered)
    vInfo_capacity_consumed_on = str(round(df_vInfo_filtered_on['In Use MiB'].sum() / 1048576,2))+" TiB"
    vInfo_capacity_consumed_off = str(round(df_vInfo_filtered_off['In Use MiB'].sum() / 1048576,2))+" TiB"
    vInfo_capacity_consumed_total = str(round(df_vInfo_filtered['In Use MiB'].sum() / 1048576,2))+" TiB"
    vInfo_capacity_on = str(round(df_vInfo_filtered_on['Provisioned MiB'].sum() / 1048576,2))+" TiB"
    vInfo_capacity_off = str(round(df_vInfo_filtered_off['Provisioned MiB'].sum() / 1048576,2))+" TiB"
    vInfo_capacity_total = str(round(df_vInfo_filtered['Provisioned MiB'].sum() / 1048576,2))+" TiB"
    
    vInfo_first_column_df = {'': [
            "Capacity Consumed (On)", "Capacity Consumed (Off/Suspended)", "Capacity Consumed (Total)", 
            "Capacity provisioned (On)", "Capacity provisioned (Off/Suspended)", "Capacity provisioned (Total)"
        ]}
    vInfo_df = pd.DataFrame(vInfo_first_column_df)
    vInfo_second_column_df = [
            vInfo_capacity_consumed_on, vInfo_capacity_consumed_off, vInfo_capacity_consumed_total,
            vInfo_capacity_on, vInfo_capacity_off, vInfo_capacity_total
        ]
    vInfo_df.loc[:,'Werte'] = vInfo_second_column_df

    return vPartition_df, vDisk_df,vDataStore_df, vm_storage_df, vInfo_df

# Generate vDisk bar chart diagram in vStorage section
@st.cache(allow_output_mutation=True)
def generate_vDisk_bar_chart(df_vDisk_filtered):

    vDisk_df = pd.DataFrame()
    vDisk_df["Capacity GiB"] = df_vDisk_filtered["Capacity MiB"] / 1024
    bins = [0, 10.01, 100.01, 1024.01,2048.01, 4096.01, 63488.01] # As lower end will be included in bin added .01 to ensure correct bins
    labels = ['0 - 10 GB', '>10 - 100 GB', '>100 GB - 1 TB', '>1 TB - 2 TB', '>2 TB - 4TB', '> 4 TB']
    vDisk_df['label'] = pd.cut(vDisk_df['Capacity GiB'], bins=bins, labels=labels, include_lowest=True)
    vDisk_df = vDisk_df.groupby('label').size().reset_index(name='counts')
    bar_chart = px.bar(
                vDisk_df,
                x = 'label',
                y = 'counts'
            )
    bar_chart.update_traces(marker_color='#034EA2')
    bar_chart.update_layout(
            margin=dict(l=10, r=10, t=20, b=10,pad=4), autosize=True, height = 375, 
            xaxis={'visible': True, 'showticklabels': True, 'title':'vDisk Capacity'},
            yaxis={'visible': True, 'showticklabels': True, 'title':'Anzahl vDisk'},
        )
    bar_chart.update_traces(texttemplate='%{y}', textposition='outside',textfont_size=14, cliponaxis=False)
    bar_chart.add_layout_image(background_image)
    bar_chart_config = { 'staticPlot': True}

    return bar_chart, bar_chart_config

# Generate VM Storage chart diagram in vStorage section
@st.cache(allow_output_mutation=True)
def generate_vm_storage_chart(vm_storage_df):
    
    vm_capacity_provisioned_overall = float(vm_storage_df.iloc[8]['Werte'].strip(' TiB'))
    vm_capacity_consumed_overall = float(vm_storage_df.iloc[5]['Werte'].strip(' TiB'))
    type_first_column = {'Type': ["Provisioned", "Consumed"]}
    storage_df = pd.DataFrame(type_first_column)
    values_second_column = [vm_capacity_provisioned_overall, vm_capacity_consumed_overall]
    storage_df.loc[:,'Werte'] = values_second_column
    storage_chart = px.funnel(storage_df, x='Type', y='Werte')
    storage_chart.update_layout(
            margin=dict(l=10, r=10, t=10, b=10,pad=4), autosize=True, height=295,
            xaxis={'visible': False, 'showticklabels': True}, yaxis={'visible': False, 'showticklabels': False}
            )    
    storage_chart.update_traces(marker_color=['#034EA2', '#B0D235'],texttemplate = "<b>%{label}:</b><br> %{value} TiB", textposition='inside',textfont_size=18, cliponaxis= False)
    storage_chart_config = { 'staticPlot': True} 
    storage_chart.add_layout_image(background_image)    

    return storage_chart, storage_chart_config

# Calculate vCPU Sizing Results
# Do not use @st.cache here
def calculate_sizing_result_vCPU(vCPU_provisioned_df):

    if st.session_state['vCPU_selectbox'] == 'vCPUs VMs - On *':
        vCPU_value = vCPU_provisioned_df.data.loc[0].values[1]
    elif st.session_state['vCPU_selectbox'] == 'vCPUs VMs - Total (On/Off/Suspended)':
        vCPU_value = vCPU_provisioned_df.data.loc[3].values[1]

    # Roundup both values and convert to int
    vCPU_value = int(np.ceil(vCPU_value))
    vCPU_value_calc = int(np.ceil(vCPU_value*(1+(int(st.session_state['vCPU_slider'])/100))))

    st.session_state['vCPU_basis'] = str(vCPU_value)
    st.session_state['vCPU_final'] = str(vCPU_value_calc)
    st.session_state['vCPU_growth'] = str(vCPU_value_calc-vCPU_value)

# Calculate vRAM Sizing Results
# Do not use @st.cache here
def calculate_sizing_result_vRAM(vRAM_provisioned_df):

    if st.session_state['vRAM_selectbox'] == 'vMemory VMs - On *':
        vRAM_value = vRAM_provisioned_df.data.loc[0].values[1]
    elif st.session_state['vRAM_selectbox'] == 'vMemory VMs - Total (On/Off/Suspended)':
        vRAM_value = vRAM_provisioned_df.data.loc[3].values[1]

    vRAM_value = round(vRAM_value,2)
    vRAM_value_calc = int(np.ceil(vRAM_value*(1+(int(st.session_state['vRAM_slider'])/100))))
    vRAM_value_diff = round((vRAM_value_calc-vRAM_value),2)

    st.session_state['vRAM_basis'] = str(vRAM_value)
    st.session_state['vRAM_final'] = str(vRAM_value_calc)
    st.session_state['vRAM_growth'] = str(vRAM_value_diff)

# Calculate vStorage Sizing Results
# Do not use @st.cache here
def calculate_sizing_result_vStorage(vm_storage_df):

    if st.session_state['vStorage_selectbox'] == 'Consumed VM Storage - Total (On/Off/Suspended) *':
        vStorage_value = float(vm_storage_df.iloc[5]['Werte'].strip(' TiB'))
    elif st.session_state['vStorage_selectbox'] == 'Consumed VM Storage - On':
        vStorage_value = float(vm_storage_df.iloc[3]['Werte'].strip(' TiB'))
    elif st.session_state['vStorage_selectbox'] == 'Provisioned VM Storage - Total (On/Off/Suspended)':
        vStorage_value = float(vm_storage_df.iloc[8]['Werte'].strip(' TiB'))
    elif st.session_state['vStorage_selectbox'] == 'Provisioned VM Storage - On':
        vStorage_value = float(vm_storage_df.iloc[6]['Werte'].strip(' TiB'))

    # Roundup values and convert to int
    vStorage_value = round(vStorage_value,2)
    vStorage_value_calc = int(np.ceil(vStorage_value*(1+(int(st.session_state['vStorage_slider'])/100))))
    vStorage_value_diff = round((vStorage_value_calc-vStorage_value),2)

    st.session_state['vStorage_basis'] = str(vStorage_value)
    st.session_state['vStorage_final'] = str(vStorage_value_calc)
    st.session_state['vStorage_growth'] = str(vStorage_value_diff)

# vCPU bar chart in the vCPU section
@st.cache(allow_output_mutation=True)
def generate_cpu_bar_chart(df_vCPU_filtered):

    df_test = df_vCPU_filtered.groupby('CPUs').size().reset_index(name='counts')
    # Make Column as int then as str in order for xaxis to show only available values rather than gaps with missing values
    df_test['CPUs'] = df_test['CPUs'].astype(str) 
    bar_chart = px.bar(
                df_test,
                x = 'CPUs',
                y = 'counts',
            )
    bar_chart.update_traces(marker_color='#034EA2')
    bar_chart.update_layout(
            margin=dict(l=10, r=10, t=20, b=10,pad=4), autosize=True, height = 375, 
            xaxis={'visible': True, 'showticklabels': True, 'title':'CPUs / VM','tickmode':'linear'},
            yaxis={'visible': True, 'showticklabels': True, 'title':'Anzahl VMs'}
        )    

    bar_chart.update_traces(texttemplate='%{y}', textposition='outside',textfont_size=14, cliponaxis=False)
    bar_chart.add_layout_image(background_image)
    bar_chart_config = { 'staticPlot': True}

    return bar_chart, bar_chart_config

# vMemory bar chart in the vMemory section
@st.cache(allow_output_mutation=True)
def generate_memory_bar_chart(df_vMemory_filtered):
    # Generate new df only with Size Mib / GiB and counts as columns
    df_test = df_vMemory_filtered.groupby('Size MiB').size().reset_index(name='counts')
    # Calculate from MiB to GiB & rename column
    df_test.loc[:,"Size MiB"] = df_test["Size MiB"] / 1024 # Use GiB instead of MiB
    df_test.rename(columns={'Size MiB': 'Size GiB'}, inplace=True) # Rename Column
    # Make Column as int then as str in order for xaxis to show only available values rather than gaps with missing values
    df_test['Size GiB'] = df_test['Size GiB'].astype(int).astype(str) 

    bar_chart = px.bar(
                df_test,
                x = 'Size GiB',
                y = 'counts'
            )
    bar_chart.update_layout(
            margin=dict(l=10, r=10, t=20, b=10,pad=4), autosize=True, height = 375, 
            xaxis={'visible': True, 'showticklabels': True, 'title':'vMemory GiB / VM'},
            yaxis={'visible': True, 'showticklabels': True, 'title':'Anzahl VMs'},
        )
    bar_chart.update_traces(texttemplate='%{y}', textposition='outside',textfont_size=14, cliponaxis=False,marker_color='#034EA2')
    bar_chart.add_layout_image(background_image)
    bar_chart_config = { 'staticPlot': True}

    return bar_chart, bar_chart_config

# Send Slack Message
# NO cache function!
def send_slack_message_and_set_session_state(payload, uploaded_file):
    # store uploaded filename as sessionstate variable in order to block
    st.session_state[uploaded_file.name] = True  
    # Send a Slack message to a channel via a webhook. 
    webhook = aws_access_key_id=st.secrets["slack_webhook_url"]
    payload = {"text": payload}
    requests.post(webhook, json.dumps(payload))