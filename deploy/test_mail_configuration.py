import io
import unittest
from dotenv import dotenv_values
from configure_mail_remote import serialize_environment

class MailConfigurationTests(unittest.TestCase):
    def test_credentials_are_literal_and_existing_keys_preserved(self):
        password='example-$value-${UNSET}-"quote"-\\slash-\'single'
        result=serialize_environment('DATABASE_URL=postgresql://unchanged\nJWT_SECRET=existing\n',{'MAIL_PASSWORD':password})
        parsed=dotenv_values(stream=io.StringIO(result),interpolate=False)
        self.assertEqual(parsed['MAIL_PASSWORD'],password)
        self.assertEqual(parsed['DATABASE_URL'],'postgresql://unchanged')
        self.assertEqual(parsed['JWT_SECRET'],'existing')

    def test_newlines_are_rejected(self):
        with self.assertRaises(ValueError):
            serialize_environment('',{'MAIL_PASSWORD':'secret\nADMIN_EMAILS=other'})

if __name__=='__main__': unittest.main()
