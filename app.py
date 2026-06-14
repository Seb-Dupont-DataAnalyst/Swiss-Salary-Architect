import pandas as pd
from flask import Flask, render_template, request, jsonify
from flask import Flask
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/calculate', methods=['POST'])
def calculate():
    try:
        data = request.get_json()
        canton_selectionne = data.get('canton', 'GE').strip()
        salary = float(data.get('salary', 0))
        rent_user = float(data.get('rent', 0))
        leisure = float(data.get('leisure', 0))

        # 1. CHARGEMENT DES DONNÉES DE BASE
        import csv
        rows = []
        with open('swiss_master_data.csv', mode='r', encoding='utf-8-sig') as f:
            content = [line.strip().replace('"', '') for line in f if line.strip()]
            reader = csv.DictReader(content, delimiter=';')
            for row in reader:
                rows.append(row)
        
        df = pd.DataFrame(rows)
        df.columns = [c.strip() for c in df.columns]
        df['Canton'] = df['Canton'].str.strip()
        
        target_row = df[df['Canton'] == canton_selectionne]
        canton_data = df.iloc[0] if target_row.empty else target_row.iloc[0]

        def to_float(val):
            return float(str(val).replace(',', '.'))

        premium_max = to_float(canton_data['Premium_Max'])
        
        # 2. DÉDUCTIONS SOCIALES (AVS, AI, APG, AC, LPP)
        social_deductions = salary * 0.134
        net_imposable = max(0.0, salary - social_deductions)
        
        # 3. MOTEUR FISCAL PROGRESSIF ET DÉCOUPAGE (Simulation AFC 2026)
        # A. Impôt Fédéral Direct (IFD) - Barème progressif national simulé
        if net_imposable <= 15000:
            fed_tax = 0.0
        elif net_imposable <= 40000:
            fed_tax = (net_imposable - 15000) * 0.0077
        elif net_imposable <= 70000:
            fed_tax = 192.5 + (net_imposable - 40000) * 0.0088
        elif net_imposable <= 100000:
            fed_tax = 456.5 + (net_imposable - 70000) * 0.0264
        elif net_imposable <= 150000:
            fed_tax = 1248.5 + (net_imposable - 100000) * 0.055
        elif net_imposable <= 250000:
            fed_tax = 3998.5 + (net_imposable - 150000) * 0.088
        else:
            fed_tax = 12798.5 + (net_imposable - 250000) * 0.11

        # B. Impôt Cantonal de Base (Progressivité modélisée selon l'agressivité du canton)
        # Recherche de l'indice de base du canton dans ton CSV (ex: Tax_Rate_Base)
        tax_rate_base = to_float(canton_data['Tax_Rate_Base'])
        
        # Facteur de progressivité : les hauts salaires paient un taux plus proche du max
        progressivity_factor = min(1.3, 0.5 + (net_imposable / 250000) * 0.5)
        cantonal_base_rate = tax_rate_base * progressivity_factor
        
        # Séparation Canton / Commune (généralement réparti à parts presque égales 55% / 45%)
        cantonal_tax = net_imposable * cantonal_base_rate * 0.55
        communal_tax = net_imposable * cantonal_base_rate * 0.45

        # Somme totale de l'impôt
        tax_amount = fed_tax + cantonal_tax + communal_tax

        # LE VRAI NET EN BANQUE (Brut - Social - Impôt)
        real_net_bancaire = net_imposable - tax_amount
        
        # FRAIS FIXES ET ÉPARGNE (calculés sur ce qu'il reste)
        health_insurance_annual = premium_max * 12
        savings = real_net_bancaire - rent_user - health_insurance_annual - leisure
        
        return jsonify({
            "values": [
                social_deductions, 
                real_net_bancaire, # On envoie le vrai Net bancaire à l'index 1 (qui alimente le nœud 2)
                tax_amount, 
                rent_user, 
                health_insurance_annual, 
                leisure, 
                savings
            ],
            # On injecte le découpage précis pour pouvoir l'afficher au besoin (Tippy tooltip ou détails)
            "tax_details": {
                "federal": round(fed_tax),
                "cantonal": round(cantonal_tax),
                "communal": round(communal_tax)
            },
            "tax_rate": round((tax_amount / salary) * 100, 1) if salary > 0 else 0,
            "savings_rate": round((savings / salary) * 100, 1) if salary > 0 else 0,
            "is_deficit": savings < 0
        })

    except Exception as e:
        print(f"--- ERREUR FISCALE --- : {str(e)}")
        return jsonify({"error": str(e)}), 500
    
@app.route('/get_canton_defaults')
def get_defaults():
    canton_code = request.args.get('canton', 'GE')
    df = pd.read_csv('swiss_master_data.csv', sep=';')
    row = df[df['Canton'] == canton_code].iloc[0]
    return jsonify({
        "rent": float(row['Rent_3_5_Rooms']),
        "premium": float(row['Premium_Max']),
        "cost_index": float(row.get('Cost_of_Living_Factor', 1.0)) # Sécurité si colonne absente
    })

@app.route('/get_all_cantons')
def get_all_cantons():
    import pandas as pd
    df = pd.read_csv('swiss_master_data.csv', sep=';')
    return df.to_json(orient='records')

@app.route('/calculateur')
@app.route('/observatoire')
def spa_pages():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)
