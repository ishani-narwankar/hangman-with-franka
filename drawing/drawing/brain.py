import rclpy
from rclpy.node import Node
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup

from std_srvs.srv import Empty
from matplotlib.font_manager import FontProperties
from matplotlib.textpath import TextToPath
from brain_interfaces.msg import Cartesian
from brain_interfaces.srv import BoardTiles
from gameplay_interfaces.msg import LetterMsg
# from character_interfaces.alphabet import alphabet
from geometry_msgs.msg import Pose, Point, Quaternion

from enum import Enum, auto


class State(Enum):
    INITIALIZE = auto(),
    CALIBRATE = auto(),
    SETUP = auto(),
    WAITING = auto(),
    LETTER = auto()


class Brain(Node):

    def __init__(self):
        super().__init__("Brain")

        self.timer_callback_group = MutuallyExclusiveCallbackGroup()

        self.create_timer(0.01, self.timer_callback, self.timer_callback_group)

        # create publishers

        self.moveit_mp_pub = self.create_publisher(
            Pose, '/moveit_mp', 10)

        self.cartesian_mp_pub = self.create_publisher(
            Cartesian, '/cartesian_mp', 10)

        # create services

        self.test_service = self.create_service(
            Empty, '/test_brain', self.test_service_callback)
        self.board_service = self.create_client(
            BoardTiles, '/board_tiles') # create custom service type
        self.ocr_service = self.create_service(
            Empty, '/ocr_service', self.test_service_callback)
        
        # Create subscription from hangman.py
        self.hangman = self.create_subscription(
            LetterMsg, '/writer', callback=self.hangman_callback, qos_profile=10)

        # define global variables

        self.home_position = Pose(
            position=Point(x=-0.5, y=0.0, z=0.4),
            orientation=Quaternion(x=1.0, y=0.0, z=0.0, w=0.0)
        )
        self.alphabet = {}
        self.scale_factor = 0.01

        self.state = State.INITIALIZE

    def create_letters(self):
        """Create the dictionary of bubble letters"""

        letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        for i in range(0,len(letters)):
            letter = letters[i]
            fp = FontProperties(family="MS Gothic", style="normal")
            verts, codes = TextToPath().get_text_path(fp, letters[i])
            xlist = []
            ylist = []
            for j in range(0,len(verts) - 1):
                # if verts[j][0] > 0: Commented out because I want to keep the 0,0 for lifting off the board
                xlist.append(verts[j][0])
                ylist.append(verts[j][1])
            point_dict = {letter: {'xlist': xlist,'ylist':ylist}}
            self.alphabet.update(point_dict)
    
    def coords_to_poses(self, letter, tilepose:Pose):
        # get the coordiantes for the letter from the dictionary
        xcoord = self.alphabet[letter]['xlist']
        ycoord = self.alphabet[letter]['ylist']
        poses = []
        # TODO: write a for loop to create a list of Pose() from the coords
        for i in range(0,len(xcoord)):
            if xcoord[i] > 0 and ycoord[i] > 0:
                p = Point(x=tilepose.position.x,
                        y=tilepose.position.y + (xcoord[i] * self.scale_factor),
                        z=tilepose.position.z + (ycoord[i] * self.scale_factor))
                quat = tilepose.orientation
                point_pose = Pose(position=p, orientation=quat)
            else:
                p = Point(x=tilepose.position.x - 0.2,
                        y=tilepose.position.y + (xcoord[i] * self.scale_factor),
                        z=tilepose.position.z + (ycoord[i] * self.scale_factor))
                quat = tilepose.orientation
                point_pose = Pose(position=p, orientation=quat)
            poses.append(point_pose)
                
    def test_service_callback(self, request, response):

        self.state = State.LETTER

        return response
    
    # def board_service_callback(self, request, response):
    #     """Callback for the service to get the board tile pose"""
    
    def hangman_callback(self, msg:LetterMsg):
        """Callback when feedback is given from hangman"""

        # establishes a global message variable for the duration of the letter state
        self.last_message = msg
        # switches to letter
        self.state = State.LETTER

    def timer_callback(self):
        if self.state == State.INITIALIZE:

            # publish the message, draw.py is a subscriber
            self.moveit_mp_pub.publish(self.home_position)

            # its possible this message is sent too fast, and that draw.py
            # doesn't receive it, just keep in mind.
            
            # Moves to the tag calibration state once the robot has reached the home position
            self.state = State.CALIBRATE

        elif self.state == State.CALIBRATE:

            self.calibrate_client() # TODO: we will need to add this client that calls the calibrate action
            # This should send the camera calibration service as well
            # TODO: Ananya can put this to have that service call how she prefers

            # moves to setup state where we draw the dashes and stuff once the calibration is complete
            self.state = State.SETUP

        elif self.state == State.SETUP:

            # TODO: Add the client/action for the robot to draw the noose and the dashes
            self.setup_client()

            # Moves to the waiting state once we are setup, and waits for something to happen from hangman.py
            self.state = State.WAITING

        elif self.state == State.LETTER:

            # This for loop will run for each thing that we need to draw based on the message sent from hangman
            # TODO We will need to consider asynchronicity, but this is the flow of info
            for j in range(0,len(self.last_message.positions)):
                # Ananya's code gives origin for the tile that we are working in reference to (taking the mode group and position in group)
                self.tile_pose:Pose = self.board_service.call_async(self.last_message.mode, self.last_message.positions[j])

                # Coords to poses takes in the letter and the pose from the board and returns a list of poses for the trajectory
                letter_poses = self.coords_to_poses(self.last_message.letter, self.tile_pose)
                start_point = Pose(
                    position=Point(x=self.tile_pose.position.x - 0.1, y=self.tile_pose.position.y, z=self.tile_pose.position.z),
                    orientation=self.tile_pose.orientation
                ) # start point given by service call TODO: Ananya, please check if this is correct for the start pos
                # I have made this start point to be 10cm behind the board facing the origin of the tile in question

                # cartesian message type packages the start point and the list of letter poses
                cartesian_msg = Cartesian(
                    poses=letter_poses, start_point=start_point)

                # publish the message, draw.py is a subscriber
                self.cartesian_mp_pub.publish(cartesian_msg)

            # TODO: Will need to add the call to start the OCR before we go to the waiting state
            self.state = State.WAITING
            
        elif self.state == State.WAITING:
            pass
