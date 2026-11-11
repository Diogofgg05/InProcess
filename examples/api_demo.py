from expecto_process_manager.plugin_api.interface import Manager

manager = Manager()
result = manager.simulate_temperature(initial_temperature=40,ambient_temperature=22,power=45,duration=120,dt=.1)
print('Energia simulada (J):',manager.calculate_energy(result.times,result.powers))
print('Temperatura final simulada (°C):',result.temperatures[-1])
print('Processos acessíveis:',len(manager.list_processes()))
