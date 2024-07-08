import logging
import sys

from check_constraints import check_mandatory_constraints, check_optional_constraints, parse_interval
from copy import deepcopy
from utils import *
from utils import read_yaml_file

class State:
    def __init__(self, predecessor = None, new_interval = None, timetable_specs = None,  initial_state = False, input_file = None, cost = 0, h = 0):
        if initial_state:
            self.prof_specs = timetable_specs[PROFESORI]
            self.room_specs = timetable_specs[SALI];
            self.stud_per_subject = timetable_specs[MATERII]
            self.intervals = timetable_specs[INTERVALE]
            self.days = timetable_specs[ZILE]

            self.placed_intervals = []
            self.map_day_interv_room = {}
            self.cost = 0
            self.h = 0
            self.order_subjects = get_best_subject(self.stud_per_subject, self.prof_specs, self.days)

            for _, info in self.prof_specs.items():
                info['Intervale'] = 7
            
            self.input_file = input_file
            return
        
        self.placed_intervals = predecessor.placed_intervals + [new_interval]
        self.map_day_interv_room = deepcopy(predecessor.map_day_interv_room)
        self.map_day_interv_room[(new_interval[0], new_interval[1],new_interval[2])] = (new_interval[3], new_interval[4])
        
        self.prof_specs = deepcopy(predecessor.prof_specs)
        self.room_specs = predecessor.room_specs
        self.days = predecessor.days

        self.stud_per_subject = deepcopy(predecessor.stud_per_subject)
        self.order_subjects = deepcopy(predecessor.order_subjects)
        self.get_ord = get_best_subject(self.order_subjects, self.prof_specs, self.days)
        self.order_subjects = self.get_ord
        self.order_subjects[new_interval[4]] = max(0, self.order_subjects[new_interval[4]] - self.room_specs[new_interval[2]]['Capacitate'])
        self.intervals = predecessor.intervals

        self.input_file = predecessor.input_file
        self.h = check_mandatory(self.convert_state(), self.prof_specs, self.room_specs, self.map_day_interv_room, self.order_subjects)
        self.cost = check_optional(self.convert_state(), self.prof_specs)

    def __str__(self):
        return pretty_print_timetable(self.convert_state(), self.input_file)
    
    def __lt__(self, other):
        if (self.h + self.cost) < (other.h + other.cost):
            return True
        elif (self.h + self.cost) > (other.h + other.cost):
            return False
        else:
            if self.cost < other.cost:
                return True
            elif self.cost > other.cost:
                return False
            else:
                cnt = 0
                for _, nr_stud in self.order_subjects.items():
                    cnt += nr_stud
                cnt1 = 0
                for _, nr_stud in other.order_subjects.items():
                    cnt1 += nr_stud
                return cnt < cnt1

    

    def gen_next_states(self):
        out = []
        for day in self.days:
            for interval in self.intervals:
                for room, room_info in self.room_specs.items():
                    if (day, interval, room) in self.map_day_interv_room:
                        continue

                    for prof, prof_info in self.prof_specs.items():
                        if prof_info['Intervale'] <= 0:
                            continue
                        
                        for subject, nr_stud in self.order_subjects.items():
                            if subject not in prof_info[MATERII] or \
                                subject not in room_info[MATERII]:
                                continue
                            
                            if nr_stud <= 0:
                                continue

                            # generate new state
                            
                            new_state = State(self, (day, interval, room, prof, subject))
                            out.append(new_state)
        return out
    
    def convert_state(self):
        aux_struct = {}
        for day in self.days:
            if day not in aux_struct:
                aux_struct[day] = {}
            for interval in self.intervals:
                tuple_interval = tuple(map(int, interval.strip('()').split(',')))
                if tuple_interval not in aux_struct[day]:
                    aux_struct[day][tuple_interval] = {}
                for room in self.room_specs.keys():
                    if room not in aux_struct[day][tuple_interval]:
                        aux_struct[day][tuple_interval][room] = {}
        for (day, interval, room), slot in self.map_day_interv_room.items():
            tuple_interval = tuple(map(int, interval.strip('()').split(',')))
            aux_struct[day][tuple_interval][room] = slot
        return aux_struct
    

def check_mandatory(timetable : {str : {(int, int) : {str : (str, str)}}}, prof_spec : dict, room_spec : dict, map_day_interval_room : dict, stud_per_subject : dict):
    '''
    Se verifică dacă orarul generat respectă cerințele obligatorii pentru a fi un orar valid.
    '''

    constrangeri_incalcate = 0

    acoperire_target = stud_per_subject
    
    acoperire_reala = {subject : 0 for subject in acoperire_target}

    ore_profesori = {prof : 0 for prof in prof_spec}

    for day in timetable:
        for interval in timetable[day]:
            profs_in_crt_interval = []
            for room in timetable[day][interval]:
                if timetable[day][interval][room]:
                    prof, subject = timetable[day][interval][room]
                    acoperire_reala[subject] += room_spec[room]['Capacitate']

                    # PROFESORUL PREDĂ 2 MATERII ÎN ACELAȘI INTERVAL
                    if prof in profs_in_crt_interval:
                        constrangeri_incalcate += 1
                    else:
                        profs_in_crt_interval.append(prof)

                    # MATERIA NU SE PREDA IN SALA
                    if subject not in room_spec[room][MATERII]:
                        constrangeri_incalcate += 1

                    # PROFESORUL NU PREDA MATERIA
                    if subject not in prof_spec[prof][MATERII]:
                        constrangeri_incalcate += 1

                    ore_profesori[prof] += 1

    # CONDITIA DE ACOPERIRE
    for subject in acoperire_target:
        if acoperire_reala[subject] < acoperire_target[subject]:
            constrangeri_incalcate += 1

    # CONDITIA DE MAXIM 7 ORE PE SĂPTĂMÂNĂ
    for prof in ore_profesori:
        if ore_profesori[prof] > 7:
            constrangeri_incalcate += 1

    return constrangeri_incalcate

def check_optional(timetable : {str : {(int, int) : {str : (str, str)}}}, prof_spec : dict):
    constrangeri_incalcate = 0
    for prof in prof_spec:
        for const in prof_spec[prof]['Constrangeri']:
            if const[0] != '!':
                continue
            else:
                const = const[1:]

                if const in timetable:
                    day = const
                    if day in timetable:
                        for interval in timetable[day]:
                            for room in timetable[day][interval]:
                                if timetable[day][interval][room]:
                                    crt_prof, _ = timetable[day][interval][room]
                                    if prof == crt_prof:
                                        constrangeri_incalcate += 1
                
                elif '-' in const:
                    interval = parse_interval(const)
                    start, end = interval

                    if start != end - 2:
                        intervals = [(i, i + 2) for i in range(start, end, 2)]
                    else:
                        intervals = [(start, end)]


                    for day in timetable:
                        for interval in intervals:
                            if interval in timetable[day]:
                                for room in timetable[day][interval]:
                                    if timetable[day][interval][room]:
                                        crt_prof, _ = timetable[day][interval][room]
                                        if prof == crt_prof:
                                            constrangeri_incalcate += 1
    return constrangeri_incalcate


def get_best_subject(stud_per_subject, prof_specs, days):
        min_subj = sorted(stud_per_subject.items(), key=lambda x:x[1])
        #sorted list of subjects by number of professors
        count_subj_in_prof = {}
        for subj in min_subj:
            count_subj_in_prof[subj[0]] = 0
            for prof in prof_specs:
                if subj[0] in prof_specs[prof][MATERII]:
                    count_subj_in_prof[subj[0]] += 1
        min_subj = sorted(min_subj, key=lambda x:count_subj_in_prof[x[0]])
        count_interval_prof_subj = {}
        for subj in min_subj:
            count_interval_prof_subj[subj[0]] = 0
            for prof in prof_specs:
                if subj[0] in prof_specs[prof][MATERII]:
                    for const in prof_specs[prof]['Constrangeri']:
                        if const[0] == '!':
                            continue
                        else:
                            if const in days:
                                for interval in prof_specs[prof]['Constrangeri']:
                                    if interval[0] != '!' and interval not in days:
                                        interval = parse_interval(interval)
                                        start, end = interval

                                        if start != end - 2:
                                            intervals = [(i, i + 2) for i in range(start, end, 2)]
                                        else:
                                            intervals = [(start, end)]

                                        count_interval_prof_subj[subj[0]] += len(intervals)
        
                            
        min_subj = sorted(min_subj, key=lambda x:count_interval_prof_subj[x[0]])
        final_min_subj = {}
        for i in min_subj:
            final_min_subj[i[0]] = i[1]
        return final_min_subj

def is_final(state):
    for _, nr_stud in state.order_subjects.items():
        if nr_stud > 0:
            return False
    return True

def hill_climbing(initial, timetable_specs, max_iters: int = 400):
    iters, states = 0, 0
    state = initial
    count = 0
    print(check_mandatory(state.convert_state(), state.prof_specs, state.room_specs, state.map_day_interv_room, state.order_subjects) + \
                                           check_optional(state.convert_state(), state.prof_specs))
    while iters < max_iters:
        allStates = State.gen_next_states(state)
        
        minConflict = (check_mandatory(state.convert_state(), timetable_specs[PROFESORI], timetable_specs[SALI], state.map_day_interv_room, state.order_subjects) + \
            check_optional(state.convert_state(), timetable_specs[PROFESORI]))
        minState = state
        for elem in allStates:
            cnt = 0
            for _, nr_stud in minState.order_subjects.items():
                cnt += nr_stud
            cnt1 = 0
            for _, nr_stud in elem.order_subjects.items():
               cnt1 += nr_stud
            if (check_mandatory(elem.convert_state(), elem.prof_specs, elem.room_specs, elem.map_day_interv_room, elem.order_subjects) + \
                check_optional(elem.convert_state(), elem.prof_specs)) < minConflict:
                minConflict = (check_mandatory(elem.convert_state(), elem.prof_specs, elem.room_specs, elem.map_day_interv_room, elem.order_subjects) + \
                                check_optional(elem.convert_state(), elem.prof_specs))
                minState = elem
            elif (check_mandatory(elem.convert_state(), elem.prof_specs, elem.room_specs, elem.map_day_interv_room, elem.order_subjects) + \
                check_optional(elem.convert_state(), elem.prof_specs)) == minConflict:
                if check_mandatory(elem.convert_state(), elem.prof_specs, elem.room_specs, elem.map_day_interv_room, elem.order_subjects) + cnt1 < \
                    check_mandatory(minState.convert_state(), minState.prof_specs, minState.room_specs, minState.map_day_interv_room, minState.order_subjects) + cnt:
                    minState = elem
                    minConflict = (check_mandatory(elem.convert_state(), elem.prof_specs, elem.room_specs, elem.map_day_interv_room, elem.order_subjects) + \
                                check_optional(elem.convert_state(), elem.prof_specs))
                elif check_mandatory(elem.convert_state(), elem.prof_specs, elem.room_specs, elem.map_day_interv_room, elem.order_subjects) + cnt1 == \
                    check_mandatory(minState.convert_state(), minState.prof_specs, minState.room_specs, minState.map_day_interv_room, minState.order_subjects) + cnt:
                    
                    if cnt > cnt1:
                        minState = elem
                        minConflict = (check_mandatory(elem.convert_state(), elem.prof_specs, elem.room_specs, elem.map_day_interv_room, elem.order_subjects) + \
                                check_optional(elem.convert_state(), elem.prof_specs))
                    elif cnt == cnt1:
                        if check_optional(elem.convert_state(), elem.prof_specs) + cnt1 < check_optional(minState.convert_state(), minState.prof_specs) + cnt:
                            minState = elem
                            minConflict = (check_mandatory(elem.convert_state(), elem.prof_specs, elem.room_specs, elem.map_day_interv_room, elem.order_subjects) + \
                                check_optional(elem.convert_state(), elem.prof_specs))

            
            states += 1
        print(states)
     
        if minState.h == 0 and minState.cost <= 1:
            if minConflict >= (check_mandatory(state.convert_state(), state.prof_specs, state.room_specs, state.map_day_interv_room, state.order_subjects) + \
                                check_optional(state.convert_state(), state.prof_specs)) and  \
                                check_mandatory_constraints(state.convert_state(), timetable_specs) == 0:
                print(check_mandatory_constraints(minState.convert_state(), timetable_specs))
                break
        if count > 50:
            list_remaining = {}
            for subj, nr_stud in minState.order_subjects.items():
                if nr_stud > 0:
                    list_remaining[subj] = nr_stud
            for subj, nr_stud in list_remaining.items():
                while minState.order_subjects[subj] > 0:
                    found = 0
                    print(minState.order_subjects[subj])
                    for day in minState.days:
                        for interval in minState.intervals:
                            for room in minState.room_specs.keys():
                                if (day, interval, room) not in minState.map_day_interv_room:
                                    for prof in minState.prof_specs.keys():
                                        minState.map_day_interv_room[(day, interval, room)] = (prof, subj)

                                        flag = 0
                                        
                                        if minState.order_subjects[subj] - minState.room_specs[room]['Capacitate'] < 0:
                                            
                                            minState.order_subjects[subj] -= minState.order_subjects[subj]
                                            flag = 1
                                        else:
                                            minState.order_subjects[subj] -= minState.room_specs[room]['Capacitate']

                                       
                                        if check_mandatory(minState.convert_state(), minState.prof_specs, minState.room_specs, minState.map_day_interv_room, minState.order_subjects) == 0:
                                            if check_optional(minState.convert_state(), minState.prof_specs) <= 1:
                                                
                                                found = 1
                                                break
                                            
                                            else:
                                                if flag == 1:
                                                    minState.order_subjects[subj] += minState.order_subjects[subj]
                                                else:
                                                    minState.order_subjects[subj] += minState.room_specs[room]['Capacitate']
                                                del minState.map_day_interv_room[(day, interval, room)]
                                        else:
                                            
                                            if flag == 1:
                                                minState.order_subjects[subj] += minState.order_subjects[subj]
                                            else:
                                                minState.order_subjects[subj] += minState.room_specs[room]['Capacitate']
                                            del minState.map_day_interv_room[(day, interval, room)]
                                if found == 1:
                                    break
                            if found == 1:
                                break
                        if found == 1:
                            break
                
        else:
            if minState.convert_state() == state.convert_state():
                count += 1
                print("Count is %d", count)
            state = minState
        iters += 1
    return is_final(state), iters, states, state


if __name__ == "__main__":

    if len(sys.argv) == 1:
        print('\nSe rulează de exemplu:\n\npython3 check_constraints.py orar_mic_exact\n')
        sys.exit(0)
    if sys.argv[1] == '-h':
        print('\nSe rulează de exemplu:\n\npython3 check_constraints.py orar_mic_exact\n')
    name = sys.argv[1]

    input_name = f'inputs/{name}.yaml'
    output_name = f'outputs/{name}.txt'

    timetable_specs = read_yaml_file(input_name)
    initial_state = State(timetable_specs=timetable_specs, initial_state=True, input_file=input_name)

    final, iters, states, state = hill_climbing(initial_state, timetable_specs=timetable_specs)
    print(final, iters, states, state)
    logging.basicConfig(filename="timetable_HC_incalcat.log", level=logging.INFO)
    logging.info(state)

    constrangeri_incalcate = check_mandatory_constraints(state.convert_state(), timetable_specs)
    print(f'\n=>\nS-au încălcat {constrangeri_incalcate} constrângeri obligatorii!')

    constrangeri_optionale = check_optional_constraints(state.convert_state(), timetable_specs)
    print(f'\n=>\nS-au încălcat {constrangeri_optionale} constrângeri optionale!')

    logging.info("S-au încălcat %s constrângeri obligatorii!", constrangeri_incalcate)
    logging.info("S-au încălcat %s constrângeri optionale!", constrangeri_optionale)

    