import os
import json
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AIRLAB_CSV = os.path.join(BASE_DIR, 'data', 'processed', 'airlab_energy', 'flights_detail.csv')
TRAJ_CSV = os.path.join(BASE_DIR, 'data', 'processed', 'trajectories', 'uav_trajectories.csv')
OUT_JSON = os.path.join(BASE_DIR, 'data', 'processed', 'energy_predictions.json')

def train_model():
    print(f"Loading AirLab dataset from {AIRLAB_CSV}...")
    try:
        df = pd.read_csv(AIRLAB_CSV)
    except FileNotFoundError:
        print("Data not found.")
        return None
    
    # We use airspeed, vertspd, diffalt, payload as features
    features = ['airspeed', 'vertspd', 'diffalt', 'payload']
    target = 'power'
    
    df = df.dropna(subset=features + [target])
    
    X = df[features]
    y = df[target]
    
    print("Training RandomForestRegressor for power prediction...")
    model = RandomForestRegressor(n_estimators=20, max_depth=10, random_state=42, n_jobs=-1)
    model.fit(X, y)
    print("Model trained successfully.")
    return model

def predict_energy(model):
    print(f"Loading generated UAV trajectories from {TRAJ_CSV}...")
    df_traj = pd.read_csv(TRAJ_CSV)
    
    # Sort to ensure chronological order along trajectory
    df_traj = df_traj.sort_values(by=['flight_id', 'timestamp'])
    
    # Approximate 2D airspeed 
    df_traj['airspeed'] = np.sqrt(df_traj['speed_x']**2 + df_traj['speed_y']**2)
    df_traj['vertspd'] = df_traj['speed_z']
    df_traj['diffalt'] = df_traj['alt_rel']
    
    # Add random payload to induce variance
    np.random.seed(42)
    unique_flights = df_traj['flight_id'].unique()
    flight_payloads = {fid: np.random.choice([0.0, 0.25, 0.5, 0.75, 1.0]) for fid in unique_flights}
    df_traj['payload'] = df_traj['flight_id'].map(flight_payloads)
    
    features = ['airspeed', 'vertspd', 'diffalt', 'payload']
    
    print("Predicting power for trajectory points...")
    df_traj['power_pred_W'] = model.predict(df_traj[features])
    
    print("Computing energy consumption and battery remaining...")
    # dt = time difference between consecutive points
    df_traj['dt'] = df_traj.groupby('flight_id')['timestamp'].diff().fillna(0.1)
    df_traj['energy_J'] = df_traj['power_pred_W'] * df_traj['dt']
    df_traj['cumulative_energy_J'] = df_traj.groupby('flight_id')['energy_J'].cumsum()
    
    results = {}
    
    for fid, group in df_traj.groupby('flight_id'):
        total_energy = group['cumulative_energy_J'].max()
        
        # We calculate battery capacity so that the trip consumes between 20% and 50% of the total capacity
        # This guarantees all drones depart at 100% and land safely
        consumption_ratio = np.random.uniform(0.2, 0.5)
        battery_capacity = max(total_energy / consumption_ratio, 1.0)
        
        battery_pct = 100.0 - (group['cumulative_energy_J'] / battery_capacity) * 100.0
        battery_pct = np.clip(battery_pct, 0, 100)
        
        # We only need the prediction outputs
        results[fid] = {
            "power": group['power_pred_W'].round(1).tolist(),
            "battery": battery_pct.round(1).tolist(),
            "payload": float(flight_payloads[fid])
        }
    
    # Write to target directory
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, 'w') as f:
        json.dump(results, f)
        
    print(f"Energy predictions generated and saved to {OUT_JSON}")

if __name__ == '__main__':
    mdl = train_model()
    if mdl is not None:
        predict_energy(mdl)
