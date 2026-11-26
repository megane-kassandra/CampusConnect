from rest_framework import serializers


class ConsentSerializer(serializers.Serializer):
    accepted = serializers.BooleanField()

    def validate_accepted(self, value):
        if value is not True:
            raise serializers.ValidationError('Consentement explicite requis.')
        return value


class VerificationSerializer(serializers.Serializer):
    challengeId = serializers.UUIDField()
    response = serializers.DictField()

    def validate_response(self, value):
        if not isinstance(value.get('response'), dict):
            raise serializers.ValidationError('Reponse WebAuthn absente.')
        if not all(isinstance(value.get(k), str) for k in ('id', 'rawId', 'type')):
            raise serializers.ValidationError('Credential WebAuthn invalide.')
        return value
