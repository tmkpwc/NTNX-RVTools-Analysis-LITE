import plotly.express as px  # pip install plotly-express
import plotly.graph_objs as go
import streamlit as st  # pip install streamlit
import custom_functions
import pandas as pd
import numpy as np
import warnings
from PIL import Image
import time
import base64

######################
# Page Config
######################
st.set_page_config(page_title="RVTools Analyse", page_icon='./style/favicon.png', layout="wide")
# Use CSS Modifications stored in CSS file            
st.markdown(f"<style>{custom_functions.local_css('style/style.css')}</style>", unsafe_allow_html=True)

######################
# Initialize variables
######################
filter_form_submitted = False
uploaded_file_valid = False
warnings.simplefilter("ignore") # Ignore openpyxl Excile File Warning while reading (no default style)

######################
# Page sections
######################
header_section = st.container() # Description of page & what it is about
upload_filter_section = st.container() # File Upload & Filter section
analysis_section = st.container() # Analysis section - either error message if wrong excel file or analysis content
sizing_section = st.container() # Sizing section

######################
# Page content
######################
with header_section:
    st.markdown("<h1 style='text-align: left; color:#034ea2;'>RVTools Analyse</h1>", unsafe_allow_html=True)
    st.markdown('Ein Hobby-Projekt von [**Martin Stenke**](https://www.linkedin.com/in/mstenke/) zur einfachen Analyse einer [**RVTools**](https://www.robware.net/rvtools/) Auswertung.')
    st.info('***Disclaimer: Hierbei handelt es sich lediglich um ein Hobby Projekt - keine Garantie auf Vollständigkeit oder Korrektheit der Auswertung / Daten.***')
    st.markdown("---")

with upload_filter_section:
    st.markdown('### **Upload & Filter**')
    column_upload, column_filter = st.columns(2)
            
    with column_upload:
        uploaded_file = st.file_uploader(label="Laden Sie Ihre Excel basierte RVTools Auswertung (> v4.1.2) hier hoch.", type=['xlsx'], help='Diesen Excel Export können Sie direkt aus RVTools als Excel Datei exportieren.')

    if uploaded_file is not None:
        with column_filter:            
                try:
                    # Store excel shortterm in AWS for debugging purposes
                    #if uploaded_file.name not in st.session_state:
                    #    custom_functions.upload_to_aws(uploaded_file)

                    # load excel, filter our relevant tabs and columns, merge all in one dataframe
                    df_vInfo, df_vCPU, df_vMemory, df_vDisk, df_vPartition, df_vHosts, df_vDataStore = custom_functions.get_data_from_excel(uploaded_file)            

                    vCluster_selected = st.multiselect(
                        "vCluster selektieren:",
                        options=sorted(df_vHosts["Cluster"].unique()),
                        default=sorted(df_vHosts["Cluster"].unique())
                    )

                    #if uploaded_file.name not in st.session_state:
                    #    slack_string = 'RVTools: '+str(df_vInfo['Cluster'].nunique())+' Cluster, '+str(df_vInfo['Host'].nunique())+' Host, '+str(df_vInfo.shape[0])+' VMs.'
                    #    custom_functions.send_slack_message_and_set_session_state(slack_string,uploaded_file)
                    
                    uploaded_file_valid = True
                    st.success("Die RVTools Auswertung wurde erfolgreich hochgeladen. Filtern Sie bei Bedarf nach einzelnen Clustern.")
                    
                except Exception as e:
                    uploaded_file_valid = False                    
                    analysis_section.error("##### FEHLER: Die hochgeladene RVTools Excel Datei konnte leider nicht ausgelesen werden. Stellen Sie bitte sicher, dass mindestens RVTools in der Version v4.1.2 (05.04.2021) oder neuer zum Einsatz kommt und die Excel Datei nicht manuell editiert wurde.")
                    analysis_section.markdown("Für eine Auslesen werden folgende Tabs & Spalten benöotigt:")
                    analysis_section.markdown("""
                        * ***vInfo***
                            * VM, Powerstate, CPUs, Memory, Provisioned MiB, In Use MiB, Datacenter, Cluster, Host, OS according to the configuration file, OS according to the VMware Tools, VM ID
                        * ***vCPU***
                            * VM, Powerstate, CPUs, Cluster, VM ID
                        * ***vMemory***
                            * VM, Powerstate, Size MiB, Cluster, VM ID
                        * ***vDisk***
                            * Powerstate, Capacity MiB, Thin, Cluster, VM ID
                        * ***vPartition***
                            * Powerstate, Capacity MiB, Consumed MiB, Cluster, VM ID
                        * ***vHosts***
                            * Cluster, Speed, # CPU, Cores per CPU, # Cores, CPU usage %, # Memory, Memory usage %, # VMs
                        * ***vDatastore***
                            *  Capacity MiB, Provisioned MiB, In Use MiB, Object ID
                        """)
                    analysis_section.markdown("---")
                    analysis_section.markdown("Im folgenden die genaue Fehlermeldung für ein Troubleshooting:")
                    analysis_section.exception(e)
                    st.session_state[uploaded_file.name] = True 
                    #custom_functions.send_slack_message_and_set_session_state('RVTools ERROR: '+str(e.args),uploaded_file)

if uploaded_file is not None and uploaded_file_valid is True and len(vCluster_selected) != 0:

    with analysis_section: 
        st.markdown("---")
        st.markdown('### Auswertung')
        
        # Declare new df for filtered vCluster selection
        df_vHosts_filtered = df_vHosts.query("`Cluster`==@vCluster_selected")
        df_vInfo_filtered = df_vInfo.query("`Cluster`==@vCluster_selected")
        df_vCPU_filtered = df_vCPU.query("`Cluster`==@vCluster_selected")       
        df_vMemory_filtered = df_vMemory.query("`Cluster`==@vCluster_selected")    
        df_vDisk_filtered = df_vDisk.query("`Cluster`==@vCluster_selected") 
        df_vPartition_filtered = df_vPartition.query("`Cluster`==@vCluster_selected")
        #vDatastore has no filled cluster name therefore no filter on Cluster level possible

        vCluster_expander = st.expander(label='vCluster Übersicht')
        with vCluster_expander:
            st.markdown(f"<h4 style='text-align: center;'>Die Auswertung umfasst <b>{ df_vInfo_filtered['Datacenter'].nunique() } Datacenter</b>, <b>{ df_vInfo_filtered['Cluster'].nunique() } Cluster</b>, <b>{ df_vInfo_filtered['Host'].nunique() } Host</b> und <b>{ df_vInfo_filtered.shape[0] } VMs</b>.</h4>", unsafe_allow_html=True)

            column_cpu, column_memory, column_storage = st.columns(3)            
            with column_cpu:
                st.markdown("<h4 style='text-align: center; color:#034ea2;'>pCPU:</h4>", unsafe_allow_html=True)
                total_ghz, consumed_ghz, cpu_percentage = custom_functions.generate_CPU_infos(df_vHosts_filtered)
                cpu_donut_chart, cpu_donut_chart_config = custom_functions.generate_donut_charts(cpu_percentage)
                st.plotly_chart(cpu_donut_chart, use_container_width=True, config=cpu_donut_chart_config)
                st.markdown(f"<p style='text-align: center;'>{consumed_ghz} GHz verwendet</p>", unsafe_allow_html=True)
                st.markdown(f"<p style='text-align: center;'>{total_ghz} GHz verfügbar</p>", unsafe_allow_html=True)                

            with column_memory:
                st.markdown("<h4 style='text-align: center; color:#034ea2;'>pMemory:</h4>", unsafe_allow_html=True)
                total_memory, consumed_memory, memory_percentage = custom_functions.generate_Memory_infos(df_vHosts_filtered)
                memory_donut_chart, memory_donut_chart_config = custom_functions.generate_donut_charts(memory_percentage)
                st.plotly_chart(memory_donut_chart, use_container_width=True, config=memory_donut_chart_config)
                st.markdown(f"<p style='text-align: center;'>{consumed_memory} GiB verwendet</p>", unsafe_allow_html=True)
                st.markdown(f"<p style='text-align: center;'>{total_memory} GiB verfügbar</p>", unsafe_allow_html=True)                

            with column_storage:
                st.markdown("<h4 style='text-align: center; color:#034ea2;'>vDatastore:</h4>", unsafe_allow_html=True)
                storage_provisioned, storage_consumed, storage_percentage = custom_functions.generate_Storage_infos(df_vDataStore)
                vDatastore_donut_chart, vDatastore_donut_chart_config = custom_functions.generate_donut_charts(storage_percentage)
                st.plotly_chart(vDatastore_donut_chart, use_container_width=True, config=vDatastore_donut_chart_config)
                st.markdown(f"<p style='text-align: center;'>{storage_consumed} TiB verwendet</p>", unsafe_allow_html=True)
                st.markdown(f"<p style='text-align: center;'>{storage_provisioned} TiB zugewiesen</p>", unsafe_allow_html=True)

        
        vHosts_expander = st.expander(label='vHosts Details')
        with vHosts_expander:

            pCPU_df, memory_df, hardware_df = custom_functions.generate_vHosts_overview_df(df_vHosts_filtered)            
            column_pCPU, column_pRAM, column_hardware = st.columns(3)
            
            with column_pCPU:
                st.markdown("<h5 style='text-align: center; color:#034ea2;'>pCPU Details:</h5>", unsafe_allow_html=True)
                st.table(pCPU_df)
            with column_pRAM:
                st.markdown("<h5 style='text-align: center; color:#034ea2;'> pMemory Details:</h5>", unsafe_allow_html=True)
                st.table(memory_df)
            with column_hardware:
                st.markdown("<h5 style='text-align: center; color:#034ea2;'>pHost Details:</h5>", unsafe_allow_html=True)
                st.table(hardware_df)
                
        VM_expander = st.expander(label='VM Details')
        with VM_expander:

            df_vInfo_filtered_vm_on = df_vInfo_filtered.query("`Powerstate`=='poweredOn'")    
            df_vInfo_filtered_vm_off = df_vInfo_filtered.query("`Powerstate`=='poweredOff'")
            df_vInfo_filtered_vm_suspended = df_vInfo_filtered.query("`Powerstate`=='suspended'")

            column_vm_on, column_vm_off, column_vm_suspended, column_vm_total = st.columns(4)            

            with column_vm_on:                    
                st.markdown(f"<h5 style='text-align: center; color:#B0D235;'>VMs On: { df_vInfo_filtered_vm_on['VM ID'].shape[0] }</h5>", unsafe_allow_html=True)

            with column_vm_off:                
                st.markdown(f"<h5 style='text-align: center; color:#F36D21;'>VMs Off: { df_vInfo_filtered_vm_off['VM ID'].shape[0] }</h5>", unsafe_allow_html=True)
            
            with column_vm_suspended:                
                st.markdown(f"<h5 style='text-align: center; color:#76787A;'>VMs Suspended: { df_vInfo_filtered_vm_suspended['VM ID'].shape[0] }</h5>", unsafe_allow_html=True)

            with column_vm_total:
                st.markdown(f"<h5 style='text-align: center; color:#034ea2;'>VMs Total: { df_vInfo_filtered['VM ID'].shape[0] }</h5>", unsafe_allow_html=True)

            st.write('---')
            
            column_top10_vCPU, column_top10_vRAM, column_top10_vStorage = st.columns(3)            

            with column_top10_vCPU:        
                st.markdown(f"<h6 style='text-align: center; color:#000000;'>Top 10 VMs: vCPU (On)</h6>", unsafe_allow_html=True)     
                top_vms_vMemory = custom_functions.generate_top10_vCPU_VMs_df(df_vInfo_filtered_vm_on)
                st.table(top_vms_vMemory)
            with column_top10_vRAM:
                st.markdown(f"<h6 style='text-align: center; color:#000000;'>Top 10 VMs: vMemory (On)</h6>", unsafe_allow_html=True)
                top_vms_vMemory = custom_functions.generate_top10_vMemory_VMs_df(df_vInfo_filtered_vm_on)
                st.table(top_vms_vMemory)
            with column_top10_vStorage:
                st.markdown(f"<h6 style='text-align: center; color:#000000;'>Top 10 VMs: vStorage consumed</h6>", unsafe_allow_html=True)
                top_vms_vStorage_consumed = custom_functions.generate_top10_vStorage_consumed_VMs_df(df_vInfo_filtered)
                st.table(top_vms_vStorage_consumed)

        guest_os_expander = st.expander(label='VM Gastbetriebssystem Details')
        with guest_os_expander:
            guest_os_df_config, guest_os_df_tools = custom_functions.generate_guest_os_df(df_vInfo_filtered)

            column_guestos_1, column_guestos_2 = st.columns(2)
            with column_guestos_1:
                st.markdown(f"<h5 style='text-align: center; color:#034ea2;'>Gastbetriebssysteme nach Configurations-File:</h5>", unsafe_allow_html=True)
                st.table(guest_os_df_config)
                st.markdown(f"<u>Gesamtanzahl VMs mit Guest OS nach Configurations-File:</u> <b>{guest_os_df_config['Guest OS'].sum()}</b>", unsafe_allow_html=True)
            with column_guestos_2:
                st.markdown(f"<h5 style='text-align: center; color:#034ea2;'>Gastbetriebssysteme nach VMware Tools:</h5>", unsafe_allow_html=True)        
                st.table(guest_os_df_tools)
                st.markdown(f"<u>Gesamtanzahl VMs mit Guest OS nach VMware Tools:</u> <b>{guest_os_df_tools['Guest OS'].sum()}</b>", unsafe_allow_html=True)

            st.write('Ein Auslesen der Gastbetriebssysteme basiert entweder auf der Konfigurationsdatei oder auf einer Auswertung der installierten VMware Tools. Ein Auslesen durch die VMware Tools ist zwar genauer, setzt aber vorraus dass passende VMware Tools installiert sind was i.d.R. nicht überall der Fall ist, daher wurde hier beides aufgelistet.')

        vCPU_expander = st.expander(label='vCPU Details')
        with vCPU_expander:            

            column_vCPU_1, column_vCPU_2 = st.columns([1,2])
            with column_vCPU_1:
                st.markdown("<h5 style='text-align: left; color:#034ea2; '><u>vCPU Auswertung</u></h5>", unsafe_allow_html=True)
                vCPU_provisioned_df = custom_functions.generate_vCPU_overview_df(df_vCPU_filtered,df_vHosts_filtered)
                st.table(vCPU_provisioned_df)
            with column_vCPU_2:
                st.markdown("<h5 style='text-align: left; color:#034ea2; '><u>vCPU-Verteilung</u></h5>", unsafe_allow_html=True)
                cpu_chart, cpu_chart_config = custom_functions.generate_cpu_bar_chart(df_vCPU_filtered)
                st.plotly_chart(cpu_chart,use_container_width=True, config=cpu_chart_config)

        vRAM_expander = st.expander(label='vMemory Details')
        with vRAM_expander:

            column_vRAM_table, column_vRAM_plot = st.columns([1,2])
            with column_vRAM_table:
                st.markdown("<h5 style='text-align: left; color:#034ea2; '><u>vMemory Auswertung</u></h5>", unsafe_allow_html=True)
                vRAM_provisioned_df = custom_functions.generate_vRAM_overview_df(df_vMemory_filtered)
                st.table(vRAM_provisioned_df)

            with column_vRAM_plot:
                st.markdown("<h5 style='text-align: left; color:#034ea2; '><u>vMemory-Verteilung</u></h5>", unsafe_allow_html=True)
                bar_chart_vMemory, vMemory_bar_chart_config = custom_functions.generate_memory_bar_chart(df_vMemory_filtered)
                st.plotly_chart(bar_chart_vMemory,use_container_width=True, config=vMemory_bar_chart_config)                

        vStorage_expander = st.expander(label='vStorage Details')
        with vStorage_expander:
                                   
            vPartition_df, vDisk_df, vDataStore_df, vm_storage_df, vInfo_df = custom_functions.generate_vStorage_overview_df(df_vDisk_filtered,df_vPartition_filtered,df_vDataStore,df_vInfo_filtered)            
                
            column_vDatastore, column_vInfo = st.columns(2)
            with column_vDatastore:
                st.markdown("<h5 style='text-align: left; color:#034ea2; '><u>vDatastore Auswertung</u></h5>", unsafe_allow_html=True)
                st.table(vDataStore_df)
                st.write('vDatastore enthält sämtliche Datastores die in vCenter hinterlegt sind. Diese lassen sich nicht ohne Weiteres auf einzelne VMs oder Cluster herunterbrechen und die Storage Kapazität kann z.B. durch lokale Datastores oder Backup Storage höher erscheinen als für den VM Workload tatsächlich benötigt.')
            with column_vInfo:
                st.markdown("<h5 style='text-align: left; color:#034ea2; '><u>vInfo Storage Auswertung</u></h5>", unsafe_allow_html=True)
                st.table(vInfo_df)
                st.write('Die vInfo Storage Informationen setzen auf zugewiesenen / verwendeten vDatastore Informationen für die VMs auf.')
            
            column_vPartition, column_vDisk_table, column_vDisk_plot = st.columns(3)
            with column_vPartition:
                st.markdown("<h5 style='text-align: left; color:#034ea2; '><u>vPartition Auswertung</u></h5>", unsafe_allow_html=True)            
                st.table(vPartition_df)
            with column_vDisk_table:
                st.markdown("<h5 style='text-align: left; color:#034ea2; '><u>vDisk Auswertung</u></h5>", unsafe_allow_html=True)
                st.table(vDisk_df)
            with column_vDisk_plot:
                st.markdown("<h5 style='text-align: left; color:#034ea2; '><u>vDisk Verteilung</u></h5>", unsafe_allow_html=True)
                bar_chart_vDisk, vDisk_bar_chart_config = custom_functions.generate_vDisk_bar_chart(df_vDisk_filtered)                
                st.plotly_chart(bar_chart_vDisk,use_container_width=True, config=vDisk_bar_chart_config)      

            st.markdown("<h5 style='text-align: left; color:#034ea2; '><u>VM Storage Auswertung</u></h5>", unsafe_allow_html=True)
            st.write('In der Regel werden bei einer Auswertung des VM Workloads die vPartition Daten herangezogen. Jedoch kann es sein, dass nicht für alle VMs die vPartition Daten vorliegen (z.B. durch fehlende Guest Tools), daher wird für diese VMs auf die vDisk Daten zurückgegriffen um so für alle VMs den Storage Bedarf bestmöglich erfassen zu können. Für diese Disk wird bei einer `provisioned` Storage Berechnung wird 100% der vDisk Kapazität angenommen, für eine `consumed` Storage Berechnung wird 80% der vDisk Kapazität angenommen.')
            
            column_vm_storage_table, column_vm_storage_chart = st.columns(2)            
            with column_vm_storage_table:
                st.table(vm_storage_df)
            with column_vm_storage_chart:
                st.markdown("<h5 style='text-align: center; color:#034ea2; '>VM Capacity - Total:</h5>", unsafe_allow_html=True)
                storage_chart, storage_chart_config = custom_functions.generate_vm_storage_chart(vm_storage_df)
                st.plotly_chart(storage_chart,use_container_width=True, config=storage_chart_config)    
   
    with sizing_section: 
        st.markdown("---")            
        st.markdown('### Sizing-Eckdaten-Berechnung')
          
        form_column_vCPU, form_column_vRAM, form_column_vStorage = st.columns(3)
        with form_column_vCPU:
            st.markdown("<h4 style='text-align: center; color:#034ea2; '><u>vCPU Sizing:</u></h4>", unsafe_allow_html=True)

            if 'vCPU_selectbox' not in st.session_state:
                st.session_state['vCPU_selectbox'] = 'vCPUs VMs - On *'
            if 'vCPU_slider' not in st.session_state:
                st.session_state['vCPU_slider'] = 10

            form_vCPU_selected = st.selectbox('vCPU Sizing Grundlage wählen:', ('vCPUs VMs - On *','vCPUs VMs - Total (On/Off/Suspended)'), key='vCPU_selectbox', on_change=custom_functions.calculate_sizing_result_vCPU(vCPU_provisioned_df))
            form_vCPU_growth_selected = st.slider('Wieviel % vCPU Wachstum?', 0, 100, key='vCPU_slider', on_change=custom_functions.calculate_sizing_result_vCPU(vCPU_provisioned_df))
            
        with form_column_vRAM:
            st.markdown("<h4 style='text-align: center; color:#034ea2; '><u>vMemory Sizing:</u></h4>", unsafe_allow_html=True)

            if 'vRAM_selectbox' not in st.session_state:
                st.session_state['vRAM_selectbox'] = 'vMemory VMs - On *'
            if 'vRAM_slider' not in st.session_state:
                st.session_state['vRAM_slider'] = 30

            form_vMemory_selected = st.selectbox('vMemory Sizing Grundlage wählen:', ('vMemory VMs - On *','vMemory VMs - Total (On/Off/Suspended)'), key='vRAM_selectbox', on_change=custom_functions.calculate_sizing_result_vRAM(vRAM_provisioned_df))
            form_vMemory_growth_selected = st.slider('Wieviel % vMemory Wachstum?', 0, 100, key='vRAM_slider', on_change=custom_functions.calculate_sizing_result_vRAM(vRAM_provisioned_df))

        with form_column_vStorage:
            st.markdown("<h4 style='text-align: center; color:#034ea2; '><u>vStorage Sizing:</u></h4>", unsafe_allow_html=True)

            if 'vStorage_selectbox' not in st.session_state:
                st.session_state['vStorage_selectbox'] = 'Consumed VM Storage - Total (On/Off/Suspended) *'
            if 'vStorage_slider' not in st.session_state:
                st.session_state['vStorage_slider'] = 20

            form_vStorage_selected = st.selectbox('vStorage Sizing Grundlage wählen:', ('Consumed VM Storage - Total (On/Off/Suspended) *', 'Consumed VM Storage - On', 'Provisioned VM Storage - Total (On/Off/Suspended)', 'Provisioned VM Storage - On'), key='vStorage_selectbox', on_change=custom_functions.calculate_sizing_result_vStorage(vm_storage_df))
            form_vStorage_growth_selected = st.slider('Wieviel % Storage Wachstum?', 0, 100, key='vStorage_slider', on_change=custom_functions.calculate_sizing_result_vStorage(vm_storage_df))
        st.markdown("""<p><u>Hinweis:</u> Die mit * markierten Optionen stellen die jeweilige Empfehlung für vCPU, vRAM und vStorage dar.</p>""", unsafe_allow_html=True)

      
        st.write('---')
        st.markdown('### Sizing-Eckdaten-Ergebnis')
        st.write('')

        type_column, result_column_vCPU, result_column_vRAM, result_column_vStorage = st.columns(4)

        with type_column:
            st.markdown(f"""<div class="container"><img class="logo-img" src="data:image/png;base64,{base64.b64encode(open("images/blank.png", "rb").read()).decode()}"></div>""", unsafe_allow_html=True)
            st.markdown("<h4 style='color:#FFFFFF;'>_</h4>", unsafe_allow_html=True)
            st.write('')
            st.markdown("<h4 style='text-align: left; color:#000000;'>Ausgangswert</h4>", unsafe_allow_html=True)
            st.write('')
            st.write('')
            st.markdown("<h4 style='text-align: left; color:#000000;'>Endwert</h4>", unsafe_allow_html=True)


        with result_column_vCPU:
            st.markdown(f"""<div class="container"><img class="logo-img" src="data:image/png;base64,{base64.b64encode(open("images/vCPU.png", "rb").read()).decode()}"></div>""", unsafe_allow_html=True)
            st.markdown("<h4 style='text-align: left; color:#034ea2;'>vCPU</h4>", unsafe_allow_html=True)

            custom_functions.calculate_sizing_result_vCPU(vCPU_provisioned_df)
            st.metric(label="", value=st.session_state['vCPU_basis']+ ' vCPUs')
            st.metric(label="", value=st.session_state['vCPU_final']+ ' vCPUs', delta=st.session_state['vCPU_growth']+ ' vCPUs')

        with result_column_vRAM:
            st.markdown(f"""<div class="container"><img class="logo-img" src="data:image/png;base64,{base64.b64encode(open("images/vRAM.png", "rb").read()).decode()}"></div>""", unsafe_allow_html=True)
            st.markdown("<h4 style='text-align: left; color:#034ea2;'>vRAM</h4>", unsafe_allow_html=True)

            custom_functions.calculate_sizing_result_vRAM(vRAM_provisioned_df)
            st.metric(label="", value=st.session_state['vRAM_basis']+" GiB")
            st.metric(label="", value=st.session_state['vRAM_final']+" GiB", delta=st.session_state['vRAM_growth']+" GiB")

        with result_column_vStorage:
            st.markdown(f"""<div class="container"><img class="logo-img" src="data:image/png;base64,{base64.b64encode(open("images/vStorage.png", "rb").read()).decode()}"></div>""", unsafe_allow_html=True)
            st.markdown("<h4 style='text-align: left; color:#034ea2;'>vStorage</h4>", unsafe_allow_html=True)            

            custom_functions.calculate_sizing_result_vStorage(vm_storage_df)  
            st.metric(label="", value=st.session_state['vStorage_basis']+" TiB")
            st.metric(label="", value=st.session_state['vStorage_final']+" TiB", delta=st.session_state['vStorage_growth']+" TiB")
