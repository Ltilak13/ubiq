// A cross-field rule that JSON Schema cannot state: max must not fall below min.
#Limits: {
	min: int & >=1
	max: int & >=min
}
