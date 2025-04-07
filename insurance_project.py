import streamlit as st
import pandas as pd
import json

DATA_FILE = "cases_data.json"

def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4,default=str)
if "data" not in st.session_state:
    st.session_state["data"] = load_data()

def format_insurer_amounts(amounts_dict):
    return "\n".join([f'"{k}": {v}' for k, v in amounts_dict.items()])


def import_excel(uploaded_file):
    if uploaded_file is not None:
        df = pd.read_excel(uploaded_file, sheet_name=None, engine="openpyxl", skiprows=1)
        data = load_data()
        duplicate_cases = set()
        duplicate_invoices = set()

        for sheet_name, sheet_df in df.items():
            sheet_df = sheet_df.fillna("")

            for _, row in sheet_df.iterrows():
                case_no = str(row.get("ABL SG Case Ref.", "")).strip()
                invoice_no = str(row.get("Invoice No", "")).strip()

                if case_no in data:
                    duplicate_cases.add(case_no)
                else:
                    insurers_infor = pro_insurers_field(row)
                    insurers_dict = pro_insurers_data(insurers_infor)
                    insurers = {k: float(v) for k, v in insurers_dict.items()}

                    date_of_loss = pro_loss_date(row)
                    data[case_no] = {
                        "clients": row.get("Clients/ Brokers", ""),
                        "insured": row.get("Insured", ""),
                        "case_title": row.get("Case Title", ""),
                        "date_of_loss": date_of_loss,
                        "insurers": insurers,
                        "invoices": []

                    }

                if not isinstance(data[case_no].get("invoices", []), list):
                    st.warning(f"Fixing invalid invoices format for case {case_no}")
                    data[case_no]["invoices"] = []

                if invoice_no:
                    existing_invoices = {inv["invoice_no"] for inv in data[case_no].get("invoices", [])}
                    if invoice_no in existing_invoices:
                        duplicate_invoices.add(invoice_no)
                    else:
                        parse_json_or_default = pro_fault_inv()

                        insurer_amounts_myr = parse_json_or_default(row.get("Insurer Amounts (MYR)", "{}"))
                        insurer_amounts_usd = parse_json_or_default(row.get("Insurer Amounts (USD)", "{}"))

                        invoice_date1 = data_inv(row)
                        invoice_date = convert_date(invoice_date1)

                        status_value = row.get("Status", "")
                        invoice_data = {
                            "invoice_no": invoice_no,
                            "Date of invoice": invoice_date,
                            "issuing office": row.get("Issuing Office", ""),
                            "Status": status_value,
                            "Total amount(MYR)": float(row.get("Invoice Amount (MYR)", 0.0000) or 0.0000),
                            "Total amount(USD)": float(row.get("Invoice Amount (USD)", 0.0000) or 0.0000),
                            "exchange rate": float(row.get("Fx Rate", 0.0000) or 0.0000),
                            "insurer amounts(MYR)": insurer_amounts_myr,
                            "insurer amounts(USD)": insurer_amounts_usd

                        }
                        data[case_no]["invoices"].append(invoice_data)
        save_data(data)

        dup_case_inv(duplicate_cases, duplicate_invoices)

def convert_date(date_str):
    try:
        dt = datetime.strptime(date_str, "%d-%b-%Y")
        return dt.strftime("%Y/%m/%d")
    except ValueError:
        return date_str


def dup_case_inv(duplicate_cases, duplicate_invoices):
    if duplicate_cases or duplicate_invoices:
        if duplicate_cases:
            st.warning(f"Duplicate cases not imported: {', '.join(duplicate_cases)}")
        if duplicate_invoices:
            st.warning(f"Duplicate invoices not imported: {', '.join(duplicate_invoices)}")
    else:
        st.success("Excel data imported successfully!")
    st.rerun()


def pro_loss_date(row):
    date_of_loss = row.get("Date of loss", "")
    if isinstance(date_of_loss, pd.Timestamp):
        date_of_loss = date_of_loss.strftime("%d-%b-%Y")
    else:
        date_of_loss = str(date_of_loss) if not pd.isna(date_of_loss) else ""
    return date_of_loss

from datetime import datetime
def data_inv(row):
    invoice_date = row.get("Date of Invoice", "")
    if isinstance(invoice_date, pd.Timestamp):
        return invoice_date.strftime("%Y-%m-%d")
    elif isinstance(invoice_date, str) and invoice_date:
        for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(invoice_date, fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
    return invoice_date


def pro_fault_inv():
    def parse_json_or_default(value, default={}):
        try:
            return json.loads(value) if value and value.startswith("{") else default
        except json.JSONDecodeError:
            return default

    return parse_json_or_default


def pro_insurers_field(row):
    insurers_value = row.get("Insurers", "")
    if pd.isna(insurers_value) or insurers_value is None:
        insurers = ""
    else:
        insurers = str(insurers_value).strip()

    return insurers


def pro_insurers_data(insurers):
    insurers_str = str(insurers).strip()
    if insurers_str.startswith("{") and insurers_str.endswith("}"):
        try:
            insurers_dict = json.loads(insurers_str.replace("'", "\""))
            return insurers_dict
        except json.JSONDecodeError:
            return {}
    else:
        insurers_list = [name.strip() for name in insurers_str.split(",") if name.strip()]
        if not insurers_list:
            return {}
        num_insurers = len(insurers_list)
        if num_insurers == 1:
            return {insurers_list[0]: 100.0}
        else:
            weight = round(100.0 / num_insurers, 2)
            insurers_dict = {name: weight for name in insurers_list}
            insurers_dict[insurers_list[-1]] = 100.0 - weight * (num_insurers - 1)

        return insurers_dict

def main_page():
    st.header("Case Management Dashboard")
    if st.button("Add New Case"):
        st.session_state.page = "new_case"
        st.session_state.temp_case = {}
        st.rerun()

    if st.button("Check invoices"):
        st.session_state.page = "invoice_list"
        all_invoices = []
        for case_data in st.session_state["data"].values():
            all_invoices.extend(case_data.get("invoices", []))
        st.session_state.temp_case["invoices"] = all_invoices
        st.rerun()

    if st.button("payment update"):
        st.session_state.page ="match_payment"
        total_invoices = []
        for case_data in st.session_state["data"].values():
            total_invoices.extend(case_data.get("invoices", []))
        st.session_state.temp_case["invoices"] = total_invoices
        st.rerun()

    uploaded_file = st.file_uploader("Import from Excel", type=["xlsx"])
    if uploaded_file and st.button("Import Data"):
        import_excel(uploaded_file)
    view_all_cases()

def check_invoices_page():
    if "page" not in st.session_state:
        st.session_state.page = "main"
    st.header("All Invoices")

    if st.button("← Return to Main Page",key="return_btn"):
        st.session_state.page = "main"
        st.rerun()

    if st.session_state.page == "invoice_list":
        invoices = st.session_state.temp_case.get("invoices", [])
        if invoices:
            df = pd.DataFrame(invoices)

            # if "verified_insurers" in df.columns:
            #     print("Verified===",df["verified_insurers"].iloc[5])
            #     print("type",type(df["verified_insurers"].iloc[5]))

            df["insurer amounts(MYR)"] = df["insurer amounts(MYR)"].apply(lambda x: ", ".join(f"{k}: {v}" for k, v in x.items()))
            df["insurer amounts(USD)"] = df["insurer amounts(USD)"].apply(lambda x: ", ".join(f"{k}: {v}" for k, v in x.items()))

            if "Status" in df.columns and "Date of invoice" in df.columns:
                filter_option = st.radio("Filter invoices by status:", ["All", "Paid", "Outstanding"])
                filter_invoices(df, filter_option)
            else:
                st.dataframe(df)
    else:
        st.write("No invoices found.")




def filter_invoices(df, filter_option):
    if filter_option == "All":
        st.dataframe(df)

    elif filter_option == "Paid":
        paid_df = df[df["Status"] == "Paid"]
        if not paid_df.empty:
            st.dataframe(paid_df)
        else:
            st.write("No paid invoices found.")

    elif filter_option == "Outstanding":
        cases = st.session_state.get("data", {})
        insurer_search = st.text_input("Search by Insurer (A, B, etc.)").strip()
        if not insurer_search:
            st.write("Please enter an insurer name to search.")
        else:
            choose_invoices = []
            for case_no,case_data in cases.items():
                if "insurers" in case_data and insurer_search in case_data["insurers"] :
                    insurers_keys = [str(key).upper() for key in case_data["insurers"].keys()]
                    if insurer_search.upper() in insurers_keys:
                        for invoice in case_data.get("invoices", []):
                            choose_invoices.append(invoice)
            if choose_invoices:
                df = pd.DataFrame(choose_invoices)
                st.write("Filtered invoices based on insurer search:")
        outstanding_df = df[df["Status"] == "Outstanding"].copy()
        outstanding_df["Date of invoice"] = pd.to_datetime(outstanding_df["Date of invoice"], errors="coerce")
        today = datetime.today()
        outstanding_df["Days Overdue"] = (today - outstanding_df["Date of invoice"]).dt.days

        categories = {
            "≤ 6 months": outstanding_df[outstanding_df["Days Overdue"] <= 180],
            "6 - 12 months": outstanding_df[
                (outstanding_df["Days Overdue"] > 180) & (outstanding_df["Days Overdue"] <= 365)],
            "12 - 18 months": outstanding_df[
                (outstanding_df["Days Overdue"] > 365) & (outstanding_df["Days Overdue"] <= 540)],
            "> 18 months": outstanding_df[outstanding_df["Days Overdue"] > 540]
        }
        for label, category_df in categories.items():
            with st.expander(f"{label} ({len(category_df)})"):
                if not category_df.empty:
                    st.dataframe(category_df)
                else:
                    st.write("No invoices in this category.")


def match_invoices_page():

    if st.button("← Return to Main Page",key="return_mip"):
        st.session_state.page = "main"
        st.rerun()
    st.header("Payment update")

    currency_choice = st.radio("Select Payment Currency", ["MYR", "USD"], key="currency_choice")
    insurer_keyword = st.text_input(" Insurer Name ", key="pay_insurer_keyword")
    insurer_amount_input = st.number_input("Received Amount", min_value=0.0, step=0.01, key="pay_insurer_amount")
    data = st.session_state.get("data", {})

    matching_invoices = []
    close_match_invoices = []
    amount_field = "insurer amounts(MYR)" if currency_choice == "MYR" else "insurer amounts(USD)"


    for case_no, case_data in data.items():
        invoices = case_data.get("invoices", [])
        for inv in invoices:
            if inv.get("Status", "Outstanding") != "Outstanding":
                continue
            insurer_amounts = inv.get(amount_field, {})
            for insurer,amount in insurer_amounts.items():
                if insurer_keyword.strip().lower() in insurer.lower():
                    if abs( amount- insurer_amount_input) < 0.01:
                        if "verified_insurers" in inv and insurer in inv["verified_insurers"]:
                            continue
                        matching_invoices.append((case_no, inv, insurer, amount))
                        break
                    elif currency_choice == "USD" and amount > insurer_amount_input and (amount - insurer_amount_input) <= 50:
                        close_match_invoices.append((case_no, inv, insurer, amount))

    if not matching_invoices and not close_match_invoices:
        st.info("No matching invoices found for the given insurer keyword and payment amount.")
        return

    if matching_invoices:
        st.subheader("Matched Invoices")
        for idx, (case_no, invoice, insurers, expected_amount) in enumerate(matching_invoices, start=1):
            st.markdown(f"**Invoice {idx}:**")
            st.write(f"**Invoice No:** {invoice.get('invoice_no', 'N/A')}")
            st.write(f"**Status:** {invoice.get('Status', 'Outstanding')}")
            st.write(f"**Matched Insurer:** {insurers}")
            st.write(f"**Expected Amount ({currency_choice}):** {expected_amount:.2f}")

            user_bank = st.selectbox("Payment to ", ["SXP", "ABL KL", "ABL LDN"], key=f"user_bank_{idx}")

            if st.button(f"Verify Payment for Invoice {invoice.get('invoice_no')}", key=f"verify_{idx}"):
                # verified_insurers = data.get(case_no, {}).get("invoices", [])
                # if isinstance(invoice.get("verified_insurers"), str):
                #     try:
                #         invoice["verified_insurers"] = json.loads(invoice["verified_insurers"])
                #     except json.JSONDecodeError:
                #         pass
                if "verified_insurers" not in invoice:
                    invoice["verified_insurers"] = {}
                invoice["verified_insurers"][insurers] = {
                    "Received Amount": expected_amount,
                    "Payment to": user_bank,
                    "currency": currency_choice,
                    "verified": True
                }
                # print("invoice=======",invoice["verified_insurers"])
                # df = pd.DataFrame(verified_insurers)
                # df["verified_insurers"] = df["verified_insurers"].apply(lambda x: format_data(x))
                # for i, inv in enumerate(verified_insurers):
                #     data[case_no]["invoices"][i]["verified_insurers"] = df.loc[i, "verified_insurers"]
                st.success(f"Insurer {insurers} marked as verified.")
                save_data(data)





    if currency_choice == "USD" and close_match_invoices:
        st.subheader("Potential Matches")
        selected_invoice = st.selectbox(
            "Select invoices:",
            [f"Invoice No: {inv.get('invoice_no', 'N/A')} - Amount: {amount:.2f} USD" for _, inv, _, amount in
             close_match_invoices],
            key="selected_close_match_invoices"
        )
        if selected_invoice:
            selected_idx = [f"Invoice No: {inv.get('invoice_no', 'N/A')} - Amount: {amount:.2f} USD" for
                            _, inv, _, amount in close_match_invoices].index(selected_invoice)
            case_no, selected_inv, selected_insurer, selected_amount = close_match_invoices[selected_idx]
            st.write(f"**Invoice No:** {selected_inv.get('invoice_no', 'N/A')}")
            st.write(f"**Payable Amount:** {selected_amount:.2f} USD")
            new_payment = st.number_input("Enter Received Amount", min_value=0.0, step=0.01, key="new_payment_amount")
            user_bank = st.selectbox("Payment to", ["SXP", "ABL KL", "ABL LDN"], key="new_payment_bank")


            if st.button("Verify Payment for Selected Invoice"):
                # verified_insurers = data.get(case_no, {}).get("invoices", [])
                # if isinstance(selected_inv.get("verified_insurers"), str):
                #     try:
                #         selected_inv["verified_insurers"] = json.loads(selected_inv["verified_insurers"])
                #     except json.JSONDecodeError:
                #         selected_inv["verified_insurers"] = {}

                if "verified_insurers" not in selected_inv:
                    selected_inv["verified_insurers"] = {}
                selected_inv["verified_insurers"][selected_insurer] = {
                    "Received Amount": new_payment,
                    "Payment to": user_bank,
                    "currency": "USD",
                    "verified": "True"
                }
                # df = pd.DataFrame(verified_insurers)
                # print("Before update:", selected_inv["verified_insurers"])
                # df["verified_insurers"] = df["verified_insurers"].apply(lambda x: format_data(x))
                # for i, inv in enumerate(verified_insurers):
                #     data[case_no]["invoices"][i]["verified_insurers"] = df.loc[i, "verified_insurers"]
                st.success(f"Insurer {selected_insurer} marked as verified.")
                save_data(data)




        for case_no, case_data in data.items():
            for inv in case_data.get("invoices", []):
                if inv.get("Status", "Outstanding") != "Outstanding":
                    continue
                insurers_myr = set(inv.get("insurer amounts(MYR)", {}).keys())
                insurers_usd = set(inv.get("insurer amounts(USD)", {}).keys())
                all_insurers = insurers_myr | insurers_usd
                verified_insurers = set(inv.get("verified_insurers", {}))

                if all_insurers and all_insurers == verified_insurers:
                    inv["Status"] = "Paid"
                    st.success("All insurer amounts verified. Invoice status updated to PAID.")


        save_data(data)


def format_data(x):
    if isinstance(x, dict):
        result = ""
        for k, v in x.items():
            value = ""
            if isinstance(v, dict):
                for x, y in v.items():
                    value += f"    {x}: {y}\n"
            result += f"{k}:\n{value}"
        return result
    return ""


def view_all_cases():
    data = load_data()

    search_query = st.text_input("Search by Case No", "").strip().lower()

    case_list = []
    display_cases(case_list, data, search_query)
    manage_case(case_list)

def manage_case(case_list):
    if case_list:
        df = pd.DataFrame(case_list)
        st.dataframe(df, use_container_width=True)

        selected_case = st.selectbox("Select a Case", df["Case No"].tolist())
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button(f"View/Edit Case", key=f"view_edit_case_{selected_case}"):
                st.session_state["page"] = "edit_case"
                st.session_state["case_no"] = selected_case
                st.rerun()

        with col2:
            if st.button("Add/view Invoice", key=f"invoice_{selected_case}"):
                st.session_state.page = "new_invoice"
                st.session_state.case_no = selected_case
                st.rerun()

        with col3:
            if st.button("Delete Case", key=f"delete_{selected_case}"):
                data = load_data()
                if selected_case in data:
                    del data[selected_case]
                    save_data(data)
                    st.success(f"Deleted case {selected_case}")
                    st.rerun()


    else:
        st.warning("No cases found")


def display_cases(case_list, data, search_query):
    for case_no, details in data.items():
        if not isinstance(details, dict):
            st.warning(f"Invalid data format for case {case_no}: Expected dict, got {type(details)}")
            continue
        if not isinstance(details.get("invoices", []), list):
            st.warning(f"Invalid invoices format for case {case_no}: Expected list, got {type(details['invoices'])}")
            details["invoices"] = []
        if search_query and search_query not in case_no.lower():
            continue
        case_list.append({
            "Case No": case_no,
            "Clients/Brokers": details.get("clients", "N/A"),
            "Insured": details.get("insured", "N/A"),
            "Case Title": details.get("case_title", "N/A"),
            "Date of Loss": details.get("date_of_loss", "N/A"),
            "Invoices no": len(details.get("invoices", []))
        })


def new_case_page():
    (case_no, case_title, clients, data,
     date_of_loss, insured,
     new_insurers, total_share) = get_insurers_infor()

    if st.button(" Save & return home"):
        save_case_detail(case_no, case_title, clients,
                         data, date_of_loss, insured, new_insurers,total_share)


def save_case_detail(case_no, case_title, clients, data, date_of_loss, insured, new_insurers,
             total_share):
    if not case_no:
        st.error("Case No is required")
        return
    if isinstance(total_share, dict):
        total_share = sum(total_share.values())
    total_share = float(total_share)
    if abs(total_share - 100.0) > 1e-4:
        st.error("Total insurers share must equal 100%")
        return

    data[case_no]={
            "case_no": case_no,
            "clients": clients,
            "insured": insured,
            "case_title": case_title,
            "date_of_loss": str(date_of_loss),
            "insurers": new_insurers
        }

    save_case(data,case_no)
    st.session_state.page = "main"
    st.rerun()


def get_insurers_infor():
    st.header("New Case Registration")
    data = load_data()
    manage_case_page(data)
    case_no = st.text_input("Case No*", key="new_case_no").strip().replace(" ", "_")
    clients = st.text_input("Clients/Brokers", key="new_clients")
    insured = st.text_input("Insured", key="new_insured")
    case_title = st.text_input("Case Title", key="new_title")
    date_of_loss = st.date_input("Date of Loss", key="new_dol")
    st.subheader("Insurers Information")
    insurers = {}
    num_insurers = st.number_input("Number of Insurers*", min_value=1, value=max(len(insurers), 1), key="num_ins")
    total_share = 0
    new_insurers = {}
    for i in range(num_insurers):
        cols = st.columns([3, 1])
        with cols[0]:
            name = st.text_input(f"Insurer {i + 1} Name",
                                 value=list(insurers.keys())[i] if i < len(insurers) else "",
                                 key=f"ins_name_{i}")
        with cols[1]:
            share = st.number_input("Share%*",
                                    min_value=0.0,
                                    max_value=100.0,
                                    step=0.1,
                                    value=list(insurers.values())[i] if i < len(insurers) else 0.0,
                                    key=f"ins_share_{i}")
        new_insurers[name] = share
        total_share += share
    return  case_no, case_title, clients, data, date_of_loss,insured, new_insurers, total_share


def manage_case_page(data):
    if st.button("← Return to Main Page"):
        if st.session_state.get('temp_case'):
            with st.expander("Do you want to save changes before leaving?", expanded=True):
                st.write("You have unsaved changes. Do you want to save before leaving?")

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Yes, Save"):
                        save_case(data)
                        st.session_state.page = "main"
                        st.rerun()

                with col2:
                    if st.button("No, Discard"):
                        st.session_state.page = "main"
                        st.rerun()
        else:
            st.session_state.page = "main"
            st.rerun()


def save_case(data,case_no):
    case_data = data.get(case_no, {})
    data[case_no] = {
        "case_no": case_no,
        "clients": case_data.get("clients", ""),
        "insured": case_data.get("insured", ""),
        "case_title": case_data.get("case_title", ""),
        "date_of_loss": str(case_data.get("date_of_loss", "")),
        "insurers": case_data.get("insurers", {}),
        "invoices": case_data.get("invoices", [])
    }


    save_data(data)

def new_invoice_page():
    global invoice_date
    st.header("Invoice Creation")
    data = load_data()
    case_no = st.session_state.case_no
    st.session_state.data = data
    if st.button("← Return to Main"):
        st.session_state.page = "main"
        st.rerun()

    st.subheader(" Saved Invoices")
    if not data.get(case_no, {}).get("invoices"):
        st.info("No invoices found.")
    else:
        display_in(case_no, data)
        edit_invoice(case_no, data)

    save_invoice(case_no,data)
    calculate_ex()

    if st.button("Save Invoice"):
        save_data(data)
        st.success("Invoice saved!")
        st.rerun()


def display_in(case_no, data):
    df_invoices = pd.DataFrame(data.get(case_no, {}).get("invoices", []))
    df_invoices["insurer amounts(MYR)"] = df_invoices["insurer amounts(MYR)"].apply(
        lambda x: ", ".join(f"{k}: {v}" for k, v in x.items()))
    df_invoices["insurer amounts(USD)"] = df_invoices["insurer amounts(USD)"].apply(
        lambda x: ", ".join(f"{k}: {v}" for k, v in x.items()))
    st.dataframe(df_invoices)

from datetime import datetime,date
def save_invoice(case_no,data):
    invoices = st.session_state.data[case_no]["invoices"]
    input_inv_no= st.text_input("Invoice No*",value=st.session_state.get("invoice_new_inv_no", ""))
    if not input_inv_no:
        st.error("Invoice No is required")
        return

    if "invoice_new_inv_date" not in st.session_state:
        st.session_state.invoice_new_inv_date = datetime.today()

    input_inv_date= st.date_input("Invoice Date*", value=st.session_state.invoice_new_inv_date or None)
    if input_inv_date :
        if isinstance(input_inv_date, (datetime, date)):
            invoice_date = input_inv_date.strftime("%Y-%m-%d")
        else:
            try:
                invoice_date = datetime.strptime(input_inv_date, "%d-%b-%Y").strftime("%Y-%m-%d")
            except ValueError:
                st.error("Invalid date format. Please enter date as DD-MMM-YYYY (e.g., 01-Jan-2024).")
                return
    else:
        st.error("Invoice date is required.")
        return

    if "sel_Status" not in st.session_state:
        st.session_state["sel_Status"] = "Outstanding"
    if "new_office" not in st.session_state:
        st.session_state["new_office"] = "ABL KL"
    st.session_state["sel_Status"] = st.selectbox("Status", ["Outstanding", "Paid"],
                                                  index=["Outstanding", "Paid"].index(st.session_state["sel_Status"]), key="status_select")
    st.session_state["new_office"] = st.selectbox("Issuing Office", ["ABL KL", "SXP", "ABL SG"],
                                                  index=["ABL KL", "SXP", "ABL SG"].index(
                                                      st.session_state["new_office"]), key="office_select")

    existing_invoice = next((inv for inv in invoices if inv["invoice_no"] == input_inv_no), None)
    invoice_no = input_inv_no if input_inv_no else existing_invoice

    invoice_data = {
        "invoice_no": input_inv_no,
        "Date of invoice":  invoice_date,
        "Status": st.session_state["sel_Status"],
        "issuing office": st.session_state["new_office"],
        "Total amount(MYR)": st.session_state.invoice_amount_myr,
        "Total amount(USD)": st.session_state.invoice_amount_usd,
        "exchange rate": st.session_state.invoice_ex_rate,
        "insurer amounts(MYR)": {},
        "insurer amounts(USD)": {}
    }
    if existing_invoice:
        index = invoices.index(existing_invoice)
        invoices[index] = invoice_data
    else:
        st.session_state.data[case_no]["invoices"].append(invoice_data)
    insurers = data[case_no].get("insurers", {})
    for name, share in insurers.items():
        cal_amount(case_no, invoice_no, name, share)


def cal_amount(case_no,invoice_no, name, share):
    invoices = st.session_state.data[case_no]["invoices"]
    invoice_data = next((inv for inv in invoices if inv["invoice_no"] == invoice_no), None)
    if invoice_data:
        invoice_data["insurer amounts(MYR)"][name] = round(st.session_state.invoice_amount_myr * share / 100, 2)
        invoice_data["insurer amounts(USD)"][name] = round(st.session_state.invoice_amount_usd * share / 100, 2)
        index = invoices.index(invoice_data)
        st.session_state.data[case_no]["invoices"][index] = invoice_data





def edit_invoice(case_no, data):
    selected_invoice_no = selected_saved_invoices_details(data, case_no)
    if selected_invoice_no:
        selected_invoice = next((inv for inv in data[case_no]["invoices"] if
                                 inv["invoice_no"] == selected_invoice_no), None)
        if selected_invoice:
            if st.button("Delete Invoice"):
                delete_invoice(case_no, data, selected_invoice_no)
                save_data(data)
                return


def delete_invoice(case_no, data, selected_invoice_no):
    delete(data, selected_invoice_no, case_no)
    st.rerun()


def selected_saved_invoices_details(data, case_no):
    invoices = data[case_no]["invoices"]
    invoice_numbers = [inv["invoice_no"] for inv in invoices] if invoices else []
    input_invoice_no = st.selectbox("Select Invoice", invoice_numbers) if invoice_numbers else ""
    selected_invoice = next((inv for inv in invoices if inv["invoice_no"] == input_invoice_no), None)

    insurer_myr = selected_invoice.get("insurer amounts(MYR)", {})
    insurer_usd = selected_invoice.get("insurer amounts(USD)", {})

    insurer_myr_lines = [f"{k}: {v}" for k, v in insurer_myr.items()]
    insurer_usd_lines = [f"{k}: {v}" for k, v in insurer_usd.items()]

    st.subheader(" Selected Invoice Details")

    invoice_details = {
        "Invoice No":selected_invoice.get("invoice_no","N/A"),
        "Date of Invoice": selected_invoice.get("Date of invoice", "N/A"),
        "Status":selected_invoice.get("Status", "Outstanding"),
        "issuing office": selected_invoice.get("issuing office", "ABL KL"),
        "Total Amount (MYR)":selected_invoice.get("Total amount(MYR)", 0.00),
        "Total Amount (USD)":selected_invoice.get("Total amount(USD)", 0.00),
        "exchange Rate": selected_invoice.get("exchange rate", 1.00),
        "insurer amounts(MYR)":  "\n".join(insurer_myr_lines) if insurer_myr_lines else "N/A",
        "insurer amounts(USD)": "\n".join(insurer_usd_lines) if insurer_usd_lines else "N/A"
    }


    df_invoice = pd.DataFrame(list(invoice_details.items()), columns=["Field", "Value"])
    st.dataframe(df_invoice)

    return input_invoice_no


def calculate_ex():
    if "invoice_amount_myr" not in st.session_state:
        st.session_state.invoice_amount_myr = 0.00
    if "invoice_amount_usd" not in st.session_state:
        st.session_state.invoice_amount_usd = 0.00
    if "invoice_ex_rate" not in st.session_state:
        st.session_state.invoice_ex_rate = 1.0000
    temp_amount_myr = st.number_input("Amount (MYR)*", min_value=0.0, step=0.01,
                                      value=st.session_state.invoice_amount_myr, key="temp_amount_myr")
    temp_amount_usd = st.number_input("Amount (USD)*", min_value=0.0, step=0.01,
                                      value=st.session_state.invoice_amount_usd, key="temp_amount_usd")
    temp_exchange_rate = st.number_input("Exchange Rate*", min_value=0.0001, step=0.0001, format="%.4f",
                                         value=st.session_state.invoice_ex_rate, key="temp_ex_rate")
    new_amount_myr, new_amount_usd = calculate_exchange(temp_amount_myr, temp_amount_usd, temp_exchange_rate)
    if (
            (new_amount_myr != st.session_state.invoice_amount_myr) or
            (new_amount_usd != st.session_state.invoice_amount_usd) or
            (temp_exchange_rate != st.session_state.invoice_ex_rate)
    ):
        st.session_state.invoice_amount_myr = new_amount_myr
        st.session_state.invoice_amount_usd = new_amount_usd
        st.session_state.invoice_ex_rate = temp_exchange_rate
        st.rerun()
    st.write(
        f" Converted: {st.session_state.invoice_amount_myr:.2f} MYR / {st.session_state.invoice_amount_usd:.2f} USD")





def delete(data, invoice_no, case_no):
    if case_no in data and "invoices" in data[case_no]:
        invoices_before = data[case_no]["invoices"]
        data[case_no]["invoices"] = [
            inv for inv in invoices_before if inv["invoice_no"] != invoice_no
        ]
        invoices_after = data[case_no]["invoices"]

        if len(invoices_before) == len(invoices_after):
            st.error(f"Invoice {invoice_no} not found! Deletion failed.")
        else:
            save_data(data)
            st.success(f"Invoice {invoice_no} deleted!")
            st.rerun()
    else:
        st.error(f"Case {case_no} not found or has no invoices.")

def calculate_exchange(amount_myr, amount_usd, exchange_rate):
    if exchange_rate > 0:
        if amount_myr > 0 and amount_usd == 0:
            amount_usd = round(amount_myr / exchange_rate, 4)
        elif amount_usd > 0 and amount_myr == 0:
            amount_myr = round(amount_usd * exchange_rate, 4)
        elif amount_myr > 0 and amount_usd > 0:
            expected_usd = round(amount_myr / exchange_rate, 4)
            if abs(expected_usd - amount_usd) > 0.01:
                st.warning(f"Amount mismatch! Expected USD: {expected_usd}, but entered: {amount_usd}. Please verify.")
    return amount_myr, amount_usd

def edit_case_page():
    st.header("Edit Case Details")
    case_no = st.session_state.case_no
    data = load_data()
    case_data = data.get(case_no, {})

    if st.button("← Return to Main"):
        st.session_state.page = "main"
        st.rerun()

    new_case_no = st.text_input("Case No", case_no or "", key="edit_case_no")
    if new_case_no:
        new_case_no = new_case_no.strip().replace(" ", "_")
    else:
        st.warning("Case No cannot be empty!")

    case_title, clients, date_of_loss, insured = type_case_detail(case_data)

    st.subheader("Modify Insurers")
    insurers = case_data.get("insurers", {})
    num_insurers = st.number_input("Number of Insurers", min_value=1, value=max(1, len(insurers)), key="edit_num_ins")
    total_share = 0
    new_insurers = {}
    for i in range(num_insurers):
        cols = st.columns([3, 1])
        with cols[0]:
            name = st.text_input(f"Insurer {i + 1} Name",
                                 value=list(insurers.keys())[i] if i < len(insurers) else "",
                                 key=f"new_case_ins_name_{i}")
        with cols[1]:
            share = st.number_input("Share%",
                                    min_value=0.0,
                                    max_value=100.0,
                                    step=0.0001,
                                    format="%.4f",
                                    value=list(insurers.values())[i] if i < len(insurers) else 0.0,
                                    key=f"new_case_ins_share_{i}")
        new_insurers[name] = share
        total_share += share


    if st.button("Save Changes"):
        if abs(total_share - 100.0) > 1e-4:
            st.error("Total share must equal 100%")
        else:

            if new_case_no != case_no:
                if new_case_no in data:  
                    st.error("New Case No already exists")
                    return
                del data[case_no]
            data[new_case_no] = {
                "clients": clients,
                "insured": insured,
                "case_title": case_title,
                "date_of_loss": str(date_of_loss),
                "insurers": new_insurers,
                "invoices": case_data.get("invoices", [])
            }
            save_data(data)
            st.success("Case updated successfully!")
            st.session_state.page = "main"
            st.rerun()




from datetime import datetime
def type_case_detail(case_data):
    clients = st.text_input("Clients/Brokers", case_data.get("clients", ""), key="edit_clients")
    insured = st.text_input("Insured", case_data.get("insured", ""), key="edit_insured")
    case_title = st.text_input("Case Title", case_data.get("case_title", ""), key="edit_title")

    default_date = pd.to_datetime(case_data.get("date_of_loss", "2023-01-01"), errors="coerce").date()
    if pd.isna(default_date):
        default_date = datetime.date(2023, 1, 1)
    date_of_loss = st.date_input("Date of Loss", value=default_date, key="edit_date_of_loss")
    return case_title, clients, date_of_loss, insured


def main():
    st.set_page_config(layout="wide", page_title="Case Management System")

    if "page" not in st.session_state:
        st.session_state.update({
            "page": "main",
            "temp_case": {},
            "edit_case": None,
            "case_no": ""
        })

    pages = {
        "main": main_page,
        "new_case": new_case_page,
        "new_invoice": new_invoice_page,
        "edit_case": edit_case_page,
        "invoice_list": check_invoices_page,
        "match_payment": match_invoices_page
    }

    if st.session_state.page in pages:
        pages[st.session_state.page]()
    else:
        st.error("Invalid page state")


if __name__ == "__main__":
    main()


