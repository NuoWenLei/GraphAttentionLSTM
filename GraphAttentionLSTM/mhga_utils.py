from imports import tf, Iterable, date, tqdm, pd, nx, plt, np
from MultiHeadGraphAttentionLSTMCell import MultiHeadGraphAttentionLSTMCell

def create_graph_attention_lstm_model(layer_units: Iterable,
num_heads: int,
input_shape_nodes: tuple,
input_shape_edges: tuple,
sequence_length: int,
hidden_size: int,
residual: bool,
use_bias: bool,
concat_output: bool = False,
seq_wise_output: bool = True,
name: str = "GraphAttentionLSTMModel"):

	# nodes and edges inputs
	input_nodes = tf.keras.layers.Input(shape = input_shape_nodes)
	input_adj_mats = tf.keras.layers.Input(shape = input_shape_edges)

	x = input_nodes

	for i in range(len(layer_units) - 1):
		# process input for every layer with mhgaLSTMs
		mhgaLSTM_cell = MultiHeadGraphAttentionLSTMCell(
			units = layer_units[i],
			num_heads = num_heads,
			sequence_length = sequence_length,
			output_size = hidden_size,
			residual = residual,
			concat_output = concat_output,
			use_bias = use_bias,
			name = f"{name}_cell_{i}"
		)
		x = tf.keras.layers.RNN(
			mhgaLSTM_cell,
			return_sequences = True
		)((x, input_adj_mats))

	# last mhgaLSTM
	mhgaLSTM_out_cell = MultiHeadGraphAttentionLSTMCell(
		units = layer_units[-1],
		num_heads = num_heads,
		sequence_length = sequence_length,
		output_size = 1 if seq_wise_output else sequence_length,
		residual = True,
		concat_output = False,
		use_bias = True,
		name = f"{name}_cell_out"
	)

	mhgaLSTM_2 = tf.keras.layers.RNN(mhgaLSTM_out_cell)((x, input_adj_mats))

	# seq_wise_output is directly (b, 49, 1)
	# otherwise is (b, 49, 49) and average by second axis to create (b, 1, 49) or (b, 49)
	if seq_wise_output:
		output = mhgaLSTM_2
	else:
		output = tf.reduce_mean(mhgaLSTM_2, axis = -2)

	return tf.keras.models.Model(inputs = [input_nodes, input_adj_mats], outputs = output, name = name)

def load_graph_data(covid_data_path, flight_data_path):
	# load raw data
	flight_df = pd.read_csv(flight_data_path)
	covid_df = pd.read_csv(covid_data_path)
	
	# reformat dates
	covid_df["adjusted_date"] = [date(int("20" + y), int(m), int(d)).strftime("%Y/%m/%d") for m, d, y in covid_df["date"].str.split("/")]

	# find dates missing from flight data
	# filter covid_df to only include dates with flight data
	adj_dates = set(flight_df.columns[2:])
	covid_dates = set(covid_df["adjusted_date"].values)
	adj_dates_lacked = covid_dates.difference(adj_dates)
	covid_df = covid_df[~covid_df["adjusted_date"].isin(list(adj_dates_lacked))]

	# create adjacency matrices by creating networkX Graphs
	adj_matrices = []
	for d in flight_df.columns[2:]:
		G = nx.from_pandas_edgelist(df = flight_df, source = "state_from", target = "state_to", edge_attr = d)
		A = nx.adjacency_matrix(G, weight = d)
		adj_matrices.append(A.todense())
	ADJ_MATRICES = np.array(adj_matrices)

	# return results
	# ADJ_MATRICES are like edges
	# covid_df are like nodes
	return ADJ_MATRICES, covid_df

def load_sequential_data(covid_data_path, flight_data_path, num_days_per_sample = 7):
	# Load non-sequential graph data
	ADJ_MATRICES, covid_df = load_graph_data(covid_data_path, flight_data_path)

	# create unique dates
	sorted_unique_dates = np.sort(covid_df["adjusted_date"].unique())

	# init sequence lists
	print("Generating Sequential Data...")
	formatted_X_list = []
	formatted_adj_mat_list = []
	formatted_y_list_infection = []
	formatted_y_list_death = []

	# define valid cols
	valid_cols = ["Population", "confirm_value", "death_value", "infection_rate", "death_rate_from_population"]

	print("Loading Sequential Graph Data...")

	# add sequence dimension to graph data
	for i in tqdm(range(sorted_unique_dates.shape[0] - num_days_per_sample)):
		formatted_X_list.append([covid_df[covid_df["adjusted_date"] == d][valid_cols].values for d in sorted_unique_dates[i:i + num_days_per_sample]])

		formatted_adj_mat_list.append(ADJ_MATRICES[i:i + num_days_per_sample])

		formatted_y_list_infection.append(covid_df[covid_df["adjusted_date"] == sorted_unique_dates[i + num_days_per_sample]]["infection_rate"])

		formatted_y_list_death.append(covid_df[covid_df["adjusted_date"] == sorted_unique_dates[i + num_days_per_sample]]["death_rate_from_population"])

	formatted_X = np.array(formatted_X_list)
	formatted_adj_mat = np.array(formatted_adj_mat_list)
	formatted_y_infection = np.array(formatted_y_list_infection)
	formatted_y_death = np.array(formatted_y_list_death)

	# return data
	return (formatted_X, formatted_adj_mat, formatted_y_infection, formatted_y_death)

